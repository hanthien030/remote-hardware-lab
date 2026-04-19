import base64
import json
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
import shutil
from typing import Dict, List, Optional

import serial
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .protocol import CMD_ERASE, CMD_WRITE, FirmwareProtocol

app = FastAPI(
    title='Hardware Access Broker API',
    description='Service trung gian de quan ly va giao tiep voi phan cung.',
    version='0.6.0',
)


class FlashRequest(BaseModel):
    port: str
    board_type: Optional[str] = None
    baud_rate: Optional[int] = 115200
    firmware_base64: Optional[str] = None
    is_virtualized: bool
    slot_id: Optional[int] = None
    debug: bool = False
    flash_layout: Optional['FlashLayout'] = None


class InterrogateRequest(BaseModel):
    port: str


class PingRequest(BaseModel):
    port: str
    debug: bool = False


class SerialCaptureRequest(BaseModel):
    port: str
    duration_seconds: int
    baud_rate: Optional[int] = 115200
    capture_id: Optional[str] = None


class SerialCaptureStopRequest(BaseModel):
    capture_id: str


class FlashSegment(BaseModel):
    offset: str
    filename: Optional[str] = None
    base64: str


class FlashLayout(BaseModel):
    tool: Optional[str] = 'esptool.py'
    flash_mode: Optional[str] = None
    flash_freq: Optional[str] = None
    flash_size: Optional[str] = None
    segments: List[FlashSegment]


FlashRequest.model_rebuild()

_serial_capture_stop_events: Dict[str, threading.Event] = {}
_serial_capture_done_events: Dict[str, threading.Event] = {}
_serial_capture_connections: Dict[str, 'serial.Serial'] = {}
_serial_capture_lock = threading.Lock()


def flash_virtualized_device(request: FlashRequest):
    if request.slot_id is None:
        raise HTTPException(status_code=400, detail='slot_id is required for virtualized devices')

    protocol = FirmwareProtocol(port=request.port, debug=request.debug)
    try:
        if not protocol.connect():
            raise HTTPException(status_code=500, detail='Could not connect to serial port')

        if not protocol.ping():
            raise HTTPException(
                status_code=500,
                detail='Device not responding to PING. Check if device is in bootloader mode.',
            )

        erase_data = struct.pack('>B', request.slot_id)
        if not protocol.send_command(CMD_ERASE, erase_data):
            raise HTTPException(status_code=500, detail='ERASE command failed')

        firmware_bytes = base64.b64decode(request.firmware_base64)
        chunk_size = 4096
        offset = 0
        total_chunks = (len(firmware_bytes) + chunk_size - 1) // chunk_size

        for index in range(0, len(firmware_bytes), chunk_size):
            chunk = firmware_bytes[index:index + chunk_size]
            write_payload = struct.pack('>B', request.slot_id) + struct.pack('>I', offset) + chunk
            if not protocol.send_command(CMD_WRITE, write_payload):
                raise HTTPException(status_code=500, detail=f'WRITE command failed at offset {offset}')
            offset += len(chunk)

        return {
            'status': 'ok',
            'message': f'Successfully flashed {len(firmware_bytes)} bytes to slot {request.slot_id}',
            'bytes_written': len(firmware_bytes),
            'chunks_written': total_chunks,
        }
    finally:
        protocol.close()


def flash_non_virtualized_device(request: FlashRequest):
    normalized_board = (request.board_type or 'esp32').strip().lower()

    if normalized_board == 'arduino_uno':
        return flash_non_virtualized_arduino_uno(request)
    if request.flash_layout and request.flash_layout.segments:
        return flash_non_virtualized_layout(request)
    return flash_non_virtualized_esp(request)


def flash_non_virtualized_esp(request: FlashRequest):
    if not request.firmware_base64:
        raise HTTPException(status_code=400, detail='firmware_base64 is required')

    firmware_bytes = base64.b64decode(request.firmware_base64)

    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tmp_file:
        tmp_file.write(firmware_bytes)
        tmp_file_path = tmp_file.name

    try:
        command = [
            'esptool.py',
            '--port', request.port,
            'write_flash',
            '0x00000', tmp_file_path,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )

        return {
            'status': 'ok',
            'message': 'Flashed successfully using esptool.py.',
            'bytes_written': len(firmware_bytes),
            'stdout': result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        stderr_out = exc.stderr or ''
        stdout_out = exc.stdout or ''
        raise HTTPException(
            status_code=500,
            detail=f"esptool failed: {stderr_out or stdout_out or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='esptool command timed out.')
    finally:
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)


def flash_non_virtualized_arduino_uno(request: FlashRequest):
    if not request.firmware_base64:
        raise HTTPException(status_code=400, detail='firmware_base64 is required')

    firmware_bytes = base64.b64decode(request.firmware_base64)
    baud_rate = int(request.baud_rate or 115200)

    with tempfile.NamedTemporaryFile(delete=False, suffix='.hex') as tmp_file:
        tmp_file.write(firmware_bytes)
        tmp_file_path = tmp_file.name

    try:
        command = [
            'avrdude',
            '-p', 'atmega328p',
            '-c', 'arduino',
            '-P', request.port,
            '-b', str(baud_rate),
            '-U', f'flash:w:{tmp_file_path}:i',
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )

        return {
            'status': 'ok',
            'message': 'Flashed successfully using avrdude.',
            'bytes_written': len(firmware_bytes),
            'stdout': result.stdout,
            'stderr': result.stderr,
        }
    except subprocess.CalledProcessError as exc:
        stderr_out = exc.stderr or ''
        stdout_out = exc.stdout or ''
        raise HTTPException(
            status_code=500,
            detail=f"avrdude failed: {stderr_out or stdout_out or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='avrdude command timed out.')
    finally:
        if os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)


def flash_non_virtualized_layout(request: FlashRequest):
    if not request.flash_layout or not request.flash_layout.segments:
        raise HTTPException(status_code=400, detail='flash_layout.segments is required')

    tmp_dir = tempfile.mkdtemp(prefix='remotelab_flash_layout_')
    total_bytes = 0

    try:
        command = ['esptool.py', '--port', request.port, 'write_flash']

        if request.flash_layout.flash_mode:
            command.extend(['--flash_mode', request.flash_layout.flash_mode])
        if request.flash_layout.flash_freq:
            command.extend(['--flash_freq', request.flash_layout.flash_freq])
        if request.flash_layout.flash_size:
            command.extend(['--flash_size', request.flash_layout.flash_size])

        for index, segment in enumerate(request.flash_layout.segments):
            filename = segment.filename or f'segment_{index}.bin'
            safe_filename = os.path.basename(filename)
            segment_path = os.path.join(tmp_dir, safe_filename)
            segment_bytes = base64.b64decode(segment.base64)
            with open(segment_path, 'wb') as segment_file:
                segment_file.write(segment_bytes)

            total_bytes += len(segment_bytes)
            command.extend([segment.offset, segment_path])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=180,
        )

        return {
            'status': 'ok',
            'message': 'Flashed successfully using esptool.py flash layout.',
            'bytes_written': total_bytes,
            'stdout': result.stdout,
        }
    except subprocess.CalledProcessError as exc:
        stderr_out = exc.stderr or ''
        stdout_out = exc.stdout or ''
        raise HTTPException(
            status_code=500,
            detail=f"esptool failed: {stderr_out or stdout_out or 'unknown error'}",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail='esptool command timed out.')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _register_serial_capture_stop_event(capture_id: Optional[str]):
    if not capture_id:
        return None

    stop_event = threading.Event()
    with _serial_capture_lock:
        _serial_capture_stop_events[capture_id] = stop_event
    return stop_event


def _clear_serial_capture_stop_event(capture_id: Optional[str]):
    if not capture_id:
        return

    with _serial_capture_lock:
        _serial_capture_stop_events.pop(capture_id, None)


def _request_serial_capture_stop(capture_id: str) -> bool:
    with _serial_capture_lock:
        stop_event = _serial_capture_stop_events.get(capture_id)

    if not stop_event:
        return False

    stop_event.set()
    return True


def _serial_capture_stream(
    request: SerialCaptureRequest,
    stop_event: Optional[threading.Event] = None,
    done_event: Optional[threading.Event] = None,
):
    connection = None
    bytes_captured = 0

    try:
        duration_seconds = max(1, min(int(request.duration_seconds), 300))
        baud_rate = int(request.baud_rate or 115200)

        connection = serial.Serial()
        connection.port = request.port
        connection.baudrate = baud_rate
        connection.timeout = 0.5
        connection.exclusive = True
        connection.dsrdtr = False
        connection.rtscts = False
        connection.open()
        connection.dtr = False
        connection.rts = False
        connection.reset_input_buffer()
        connection.reset_output_buffer()

        # Register connection so stop handler can force-close if generator stalls
        if request.capture_id:
            with _serial_capture_lock:
                _serial_capture_connections[request.capture_id] = connection

        yield json.dumps({
            'type': 'started',
            'port': request.port,
            'duration_seconds': duration_seconds,
            'baud_rate': baud_rate,
        }) + '\n'

        deadline = time.time() + duration_seconds
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                yield json.dumps({
                    'type': 'finished',
                    'reason': 'stopped',
                    'bytes_captured': bytes_captured,
                }) + '\n'
                return

            pending = connection.in_waiting
            chunk = connection.read(pending or 1)
            if not chunk and stop_event and stop_event.is_set():
                yield json.dumps({
                    'type': 'finished',
                    'reason': 'stopped',
                    'bytes_captured': bytes_captured,
                }) + '\n'
                return
            if not chunk:
                continue

            decoded = chunk.decode('utf-8', errors='ignore')
            if not decoded:
                continue

            bytes_captured += len(chunk)
            yield json.dumps({
                'type': 'chunk',
                'chunk': decoded,
            }) + '\n'

        yield json.dumps({
            'type': 'finished',
            'reason': 'completed',
            'bytes_captured': bytes_captured,
        }) + '\n'
    except serial.SerialException as exc:
        yield json.dumps({
            'type': 'finished',
            'reason': 'serial_error',
            'error': str(exc),
            'bytes_captured': bytes_captured,
        }) + '\n'
    except Exception as exc:
        yield json.dumps({
            'type': 'finished',
            'reason': 'error',
            'error': str(exc),
            'bytes_captured': bytes_captured,
        }) + '\n'
    finally:
        if connection and connection.is_open:
            connection.close()
        _clear_serial_capture_stop_event(request.capture_id)
        if request.capture_id:
            with _serial_capture_lock:
                _serial_capture_connections.pop(request.capture_id, None)
                done_ev = _serial_capture_done_events.pop(request.capture_id, None)
            if done_ev:
                done_ev.set()


@app.get('/healthcheck', tags=['Status'])
def health_check():
    return {'status': 'ok', 'message': 'Broker is running!'}


def _empty_probe_response():
    return {
        'probe_success': False,
        'chip_type': None,
        'chip_family': None,
        'mac_address': None,
        'flash_size': None,
        'crystal_freq': None,
    }


def _extract_probe_field(pattern: str, output: str):
    match = re.search(pattern, output, re.IGNORECASE)
    if not match:
        return None
    value = (match.group(1) or '').strip()
    return value or None


def _map_chip_family(chip_type: Optional[str]):
    if not chip_type:
        return None

    normalized = chip_type.upper()
    if 'ESP32' in normalized:
        return 'esp32'
    if 'ESP8266' in normalized:
        return 'esp8266'
    return 'unknown'


@app.post('/interrogate', tags=['Device Actions'])
def interrogate_device(request: InterrogateRequest):
    command = ['esptool', '--port', request.port, 'flash-id']
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        output = '\n'.join(part for part in [result.stdout, result.stderr] if part)
        chip_type = _extract_probe_field(r'Chip type:\s*(.+)', output)
        mac_address = _extract_probe_field(
            r'MAC:\s*([0-9a-f]{2}(?::[0-9a-f]{2}){5})',
            output,
        )
        flash_size = _extract_probe_field(r'Detected flash size:\s*(.+)', output)
        crystal_freq = _extract_probe_field(r'Crystal frequency:\s*(.+)', output)

        return {
            'probe_success': True,
            'chip_type': chip_type,
            'chip_family': _map_chip_family(chip_type),
            'mac_address': mac_address.lower() if mac_address else None,
            'flash_size': flash_size,
            'crystal_freq': crystal_freq,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return _empty_probe_response()


@app.post('/ping', tags=['Debug'])
def ping_device(request: PingRequest):
    protocol = FirmwareProtocol(port=request.port, debug=request.debug)
    try:
        if not protocol.connect():
            raise HTTPException(status_code=500, detail='Could not connect to serial port')
        if not protocol.ping():
            raise HTTPException(status_code=500, detail='PING command failed')
        return {'status': 'ok', 'message': 'Device responded to PING'}
    finally:
        protocol.close()


@app.post('/flash-firmware', tags=['Firmware'])
def flash_firmware(request: FlashRequest):
    try:
        if request.is_virtualized:
            return flash_virtualized_device(request)
        return flash_non_virtualized_device(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/serial-capture', tags=['Device Actions'])
def serial_capture(request: SerialCaptureRequest):
    if not request.port:
        raise HTTPException(status_code=400, detail='port is required')
    if request.duration_seconds <= 0:
        raise HTTPException(status_code=400, detail='duration_seconds must be positive')

    stop_event = _register_serial_capture_stop_event(request.capture_id)
    done_event = None
    if request.capture_id:
        done_event = threading.Event()
        with _serial_capture_lock:
            _serial_capture_done_events[request.capture_id] = done_event

    return StreamingResponse(
        _serial_capture_stream(request, stop_event, done_event),
        media_type='application/x-ndjson',
    )


@app.post('/serial-capture/stop', tags=['Device Actions'])
def stop_serial_capture(request: SerialCaptureStopRequest):
    active_capture_found = _request_serial_capture_stop(request.capture_id)

    if active_capture_found:
        with _serial_capture_lock:
            done_ev = _serial_capture_done_events.get(request.capture_id)

        closed_naturally = False
        if done_ev:
            # Wait briefly for generator to close port naturally (via finally block)
            # Serial read timeout = 0.5s → normally done in < 1s
            closed_naturally = done_ev.wait(timeout=1.0)

        if not closed_naturally:
            # Generator's finally did not run in time (Starlette may not have called
            # aclose() after client disconnect). Force-close the serial port directly.
            with _serial_capture_lock:
                conn = _serial_capture_connections.pop(request.capture_id, None)
                _serial_capture_done_events.pop(request.capture_id, None)
            if conn:
                try:
                    if conn.is_open:
                        conn.close()
                except Exception as exc:
                    print(f'[BROKER] Force-close serial connection {request.capture_id}: {exc}')

    return {
        'status': 'ok',
        'capture_id': request.capture_id,
        'active_capture_found': active_capture_found,
    }
