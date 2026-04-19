import base64
import json
import os
import threading
import time
from typing import Dict, List, Optional, Set

import requests

from app.services import flash_queue_service, flash_serial_session
from app.ws_handlers import (
    broadcast_flash_done,
    broadcast_flash_serial_chunk,
    broadcast_flash_serial_finished,
    broadcast_flash_serial_started,
    broadcast_flash_started,
    broadcast_flash_task_update,
)

BROKER_URL = os.getenv('BROKER_URL', 'http://broker:8000')
POLL_INTERVAL_SECONDS = float(os.getenv('FLASH_QUEUE_POLL_INTERVAL', '2'))
SERIAL_CAPTURE_SECONDS = int(os.getenv('FLASH_SERIAL_CAPTURE_SECONDS', '60'))
SERIAL_BAUD_RATE = int(os.getenv('FLASH_SERIAL_BAUD_RATE', '115200'))

_worker_lock = threading.Lock()
_worker_thread = None
_worker_pid = None
_active_devices: Set[str] = set()
_active_devices_lock = threading.Lock()
_serial_stop_events: Dict[str, threading.Event] = {}
_serial_capture_ids: Dict[str, str] = {}
_serial_stop_lock = threading.Lock()


def _resolve_request_baud_rate(request_row: Dict) -> int:
    return int(request_row.get('baud_rate') or SERIAL_BAUD_RATE)


def _should_skip_startup() -> bool:
    if os.environ.get('FLASK_RUN_FROM_CLI') == 'true' and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return True
    return False


def _reserve_device(tag_name: str) -> bool:
    with _active_devices_lock:
        if tag_name in _active_devices:
            return False
        _active_devices.add(tag_name)
        return True


def _release_device(tag_name: str) -> None:
    with _active_devices_lock:
        _active_devices.discard(tag_name)


def _serial_capture_id(request_id: int) -> str:
    return f'flash-request-{request_id}'


def _register_serial_capture_runtime(tag_name: str, capture_id: str) -> threading.Event:
    with _serial_stop_lock:
        stop_event = threading.Event()
        _serial_stop_events[tag_name] = stop_event
        _serial_capture_ids[tag_name] = capture_id
        return stop_event


def _clear_serial_stop_event(tag_name: str) -> None:
    with _serial_stop_lock:
        _serial_stop_events.pop(tag_name, None)
        _serial_capture_ids.pop(tag_name, None)


def _request_broker_serial_stop(capture_id: str) -> bool:
    try:
        response = requests.post(
            f'{BROKER_URL}/serial-capture/stop',
            json={'capture_id': capture_id},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json() or {}
        return bool(payload.get('active_capture_found'))
    except Exception as exc:
        print(f'[FLASH_QUEUE] Failed to request broker serial stop for {capture_id}: {exc}')
        return False


def stop_serial_capture_for_device(tag_name: str) -> bool:
    with _serial_stop_lock:
        stop_event = _serial_stop_events.get(tag_name)
        capture_id = _serial_capture_ids.get(tag_name)

    if not stop_event and not capture_id:
        return False

    if stop_event:
        stop_event.set()
    if capture_id:
        _request_broker_serial_stop(capture_id)
    return True


def _load_flash_layout(request_row: Dict) -> Optional[Dict]:
    firmware_path = request_row.get('firmware_path')
    if not firmware_path or request_row.get('board_type') != 'esp32':
        return None

    manifest_path = os.path.splitext(firmware_path)[0] + '.flash.json'
    if not os.path.isfile(manifest_path):
        return None

    with open(manifest_path, 'r', encoding='utf-8') as manifest_file:
        manifest = json.load(manifest_file)

    firmware_dir = os.path.realpath(os.path.dirname(firmware_path))
    segments = []
    for segment in manifest.get('segments', []):
        segment_offset = segment.get('offset')
        relative_path = segment.get('path')
        if not segment_offset or not relative_path:
            continue

        candidate_path = os.path.realpath(os.path.join(os.path.dirname(firmware_path), os.path.basename(relative_path)))
        if not candidate_path.startswith(firmware_dir + os.sep):
            raise RuntimeError(f'Unsafe flash artifact path detected: {relative_path}')
        if not os.path.isfile(candidate_path):
            raise FileNotFoundError(f'Flash artifact missing: {relative_path}')

        with open(candidate_path, 'rb') as artifact_file:
            artifact_bytes = artifact_file.read()

        segments.append({
            'offset': segment_offset,
            'filename': os.path.basename(candidate_path),
            'base64': base64.b64encode(artifact_bytes).decode('ascii'),
        })

    if not segments:
        return None

    return {
        'tool': manifest.get('tool', 'esptool.py'),
        'flash_mode': manifest.get('flash_mode'),
        'flash_freq': manifest.get('flash_freq'),
        'flash_size': manifest.get('flash_size'),
        'segments': segments,
    }


def start_queue_worker_if_needed() -> bool:
    global _worker_thread, _worker_pid

    if _should_skip_startup():
        print('[FLASH_QUEUE] Skipping scheduler startup in Flask CLI reloader parent process.', flush=True)
        return False

    with _worker_lock:
        current_pid = os.getpid()
        if _worker_thread and _worker_thread.is_alive() and _worker_pid == current_pid:
            return False

        _worker_pid = current_pid
        _worker_thread = threading.Thread(
            target=_scheduler_loop,
            name='flash-queue-scheduler',
            daemon=True,
        )
        _worker_thread.start()
        print(f'[FLASH_QUEUE] Scheduler started in pid {current_pid}.', flush=True)
        return True


def _scheduler_loop():
    while True:
        try:
            candidates = flash_queue_service.list_worker_candidates()
            for candidate in candidates:
                tag_name = candidate['tag_name']
                if not _reserve_device(tag_name):
                    continue

                threading.Thread(
                    target=_process_candidate,
                    args=(candidate['id'], tag_name),
                    name=f'flash-queue-{tag_name}',
                    daemon=True,
                ).start()
        except Exception as exc:
            print(f'[FLASH_QUEUE] Scheduler error: {exc}')

        time.sleep(POLL_INTERVAL_SECONDS)


def _run_serial_capture(
    request_id: int,
    username: str,
    tag_name: str,
    port: str,
    baud_rate: int,
    total_seconds: int,
    stop_event: threading.Event,
    capture_id: str,
) -> str:
    """
    Single HTTP call to broker for the full session duration.
    Port is opened once and kept open — no reopen between segments.
    When stop is needed, closes the HTTP response so broker detects
    client disconnect and closes the serial port cleanly.
    """
    response = requests.post(
        f'{BROKER_URL}/serial-capture',
        json={
            'port': port,
            'duration_seconds': total_seconds,
            'baud_rate': baud_rate,
            'capture_id': capture_id,
        },
        stream=True,
        timeout=(10, total_seconds + 30),
    )
    response.raise_for_status()

    finish_reason = 'completed'
    last_ping_check = time.time()

    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            # Check stop_event first so worker-side stop requests short-circuit promptly.
            if stop_event.is_set():
                _, reason = flash_serial_session.should_continue(request_id)
                finish_reason = reason if reason else 'user_stopped'
                break

            # Periodic ping + should_continue check (every ~5s)
            now = time.time()
            if now - last_ping_check >= 5.0:
                flash_serial_session.maybe_send_ping(request_id)
                should_keep, reason = flash_serial_session.should_continue(request_id)
                if not should_keep:
                    finish_reason = reason
                    break
                last_ping_check = now

            if not raw_line:
                continue

            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            event_type = payload.get('type')

            if event_type == 'started':
                continue

            if event_type == 'chunk':
                chunk = payload.get('chunk') or ''
                if not chunk:
                    continue
                flash_queue_service.append_serial_log(request_id, chunk)
                broadcast_flash_serial_chunk(
                    request_id=request_id,
                    tag_name=tag_name,
                    user=username,
                    chunk=chunk,
                )
                continue

            if event_type == 'finished':
                finish_reason = payload.get('reason') or finish_reason
                break

    except Exception as exc:
        # response.close() from watcher raises ConnectionError/ReadError — treat as stop
        if stop_event.is_set():
            _, reason = flash_serial_session.should_continue(request_id)
            finish_reason = reason if reason else 'user_stopped'
        else:
            print(f'[FLASH_QUEUE] Serial capture stream error for request {request_id}: {exc}')
            finish_reason = 'error'
    finally:
        response.close()

    if finish_reason == 'stopped':
        _, reason = flash_serial_session.should_continue(request_id)
        if reason == 'user_stopped':
            finish_reason = 'user_stopped'

    return finish_reason


def _capture_serial_session(
    request_id: int,
    username: str,
    tag_name: str,
    port: str,
    baud_rate: int,
    stop_event: threading.Event,
    capture_id: str,
) -> str:
    flash_serial_session.start_session(request_id, username, tag_name, SERIAL_CAPTURE_SECONDS)
    flash_queue_service.append_log_output(
        request_id,
        f'Serial capture started on {port} with a default {SERIAL_CAPTURE_SECONDS}s hold.',
    )
    broadcast_flash_serial_started(
        request_id=request_id,
        tag_name=tag_name,
        user=username,
        duration_seconds=SERIAL_CAPTURE_SECONDS,
        baud_rate=baud_rate,
    )

    try:
        return _run_serial_capture(
            request_id=request_id,
            username=username,
            tag_name=tag_name,
            port=port,
            baud_rate=baud_rate,
            total_seconds=SERIAL_CAPTURE_SECONDS,
            stop_event=stop_event,
            capture_id=capture_id,
        )
    finally:
        flash_serial_session.end_session(request_id)


def _process_candidate(request_id: int, tag_name: str):
    stop_event = None
    try:
        claimed = flash_queue_service.claim_request_for_processing(request_id)
        if not claimed:
            return

        request_row, device = claimed
        username = request_row['user_id']
        request_baud_rate = _resolve_request_baud_rate(request_row)
        log_lines = [
            'Worker claimed request and started flashing.',
            f"Target device: {tag_name}",
            f"Target port: {device.get('port') or 'unknown'}",
            f"Board: {request_row['board_type']}",
        ]

        broadcast_flash_started(tag_name=tag_name, user=username)
        broadcast_flash_task_update(
            request_id=request_id,
            tag_name=tag_name,
            user=username,
            status='flashing',
            log='Worker claimed request and started flashing.',
        )

        if device['status'] != 'connected' or not device.get('port'):
            raise RuntimeError('Device became unavailable before flashing started')

        with open(request_row['firmware_path'], 'rb') as firmware_file:
            firmware_bytes = firmware_file.read()

        slot_id = flash_queue_service.default_slot_id_for_device(device)
        if device.get('is_virtualized') and slot_id is None:
            raise RuntimeError('Queue flashing does not support multi-slot virtualized devices yet')

        broker_payload = {
            'port': device['port'],
            'board_type': request_row['board_type'],
            'baud_rate': request_baud_rate,
            'firmware_base64': base64.b64encode(firmware_bytes).decode('ascii'),
            'is_virtualized': bool(device.get('is_virtualized')),
            'slot_id': slot_id,
        }

        if request_row['board_type'] == 'esp32' and not broker_payload['is_virtualized']:
            flash_layout = _load_flash_layout(request_row)
            if not flash_layout:
                raise RuntimeError('ESP32 flash layout metadata is missing for this firmware build')
            broker_payload['flash_layout'] = flash_layout

        broker_resp = requests.post(
            f'{BROKER_URL}/flash-firmware',
            json=broker_payload,
            timeout=150,
        )

        if not broker_resp.ok:
            try:
                broker_error = broker_resp.json()
                error_message = broker_error.get('detail') or broker_error.get('error') or broker_resp.text
            except Exception:
                error_message = broker_resp.text
            raise RuntimeError(f'Broker flash failed: {error_message}')

        broker_data = broker_resp.json()
        bytes_written = broker_data.get('bytes_written', len(firmware_bytes))
        log_lines.append(f'Flash completed successfully. Bytes written: {bytes_written}')
        capture_id = _serial_capture_id(request_id)
        stop_event = _register_serial_capture_runtime(tag_name, capture_id)
        serial_reason = _capture_serial_session(
            request_id=request_id,
            username=username,
            tag_name=tag_name,
            port=device['port'],
            baud_rate=request_baud_rate,
            stop_event=stop_event,
            capture_id=capture_id,
        )

        if serial_reason == 'completed':
            log_lines.append(f'Serial capture completed after the default {SERIAL_CAPTURE_SECONDS} seconds.')
        elif serial_reason in ('viewer_inactive', 'session_missing'):
            log_lines.append('Extended live serial session ended because no active viewer remained.')
        elif serial_reason == 'viewer_timeout':
            log_lines.append('Extended live serial session ended because the viewer did not answer ping in time.')
        elif serial_reason == 'user_stopped':
            log_lines.append('Live serial session stopped early by user.')
        elif serial_reason in ('serial_error', 'error'):
            raise RuntimeError(f'Serial capture ended due to hardware error: {serial_reason}')
        else:
            log_lines.append(f'Serial session ended: {serial_reason}.')

        broadcast_flash_serial_finished(
            request_id=request_id,
            tag_name=tag_name,
            user=username,
            reason=serial_reason,
        )

        finalized = flash_queue_service.finalize_request(
            request_id=request_id,
            username=username,
            tag_name=tag_name,
            status='success',
            log_output='\n'.join(log_lines),
        )
        if finalized:
            broadcast_flash_done(
                tag_name=tag_name,
                user=username,
                success=True,
                log='\n'.join(log_lines),
            )
            broadcast_flash_task_update(
                request_id=request_id,
                tag_name=tag_name,
                user=username,
                status='success',
                log='Flash completed successfully.',
            )
    except Exception as exc:
        error_str = str(exc) or f'Unknown error ({type(exc).__name__})'
        print(f'[FLASH_QUEUE] Request {request_id} failed: {error_str}')
        try:
            current_row = flash_queue_service.get_request_by_id(request_id)
            if current_row:
                username = current_row['user_id']
                existing_log = current_row.get('log_output') or ''
                failure_log = f'{existing_log}\n{error_str}'.strip() if existing_log else error_str

                finalized = flash_queue_service.finalize_request(
                    request_id=request_id,
                    username=username,
                    tag_name=tag_name,
                    status='failed',
                    log_output=failure_log,
                )
                if not finalized:
                    print(f'[FLASH_QUEUE] finalize_request returned False for {request_id}')
                if finalized:
                    broadcast_flash_serial_finished(
                        request_id=request_id,
                        tag_name=tag_name,
                        user=username,
                        reason='failed',
                    )
                    broadcast_flash_done(
                        tag_name=tag_name,
                        user=username,
                        success=False,
                        log=failure_log,
                    )
                    broadcast_flash_task_update(
                        request_id=request_id,
                        tag_name=tag_name,
                        user=username,
                        status='failed',
                        log=str(exc),
                    )
            else:
                print(f'[FLASH_QUEUE] Cannot finalize {request_id}: row not found')
        except Exception as finalize_exc:
            print(f'[FLASH_QUEUE] Failed to finalize request {request_id}: {finalize_exc}')
    finally:
        if stop_event is not None:
            _clear_serial_stop_event(tag_name)
        _release_device(tag_name)
