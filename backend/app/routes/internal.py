import os
import traceback

from flask import Blueprint, jsonify, request

from app.services import flash_queue_service, hardware_service
from app.services.flash_queue_worker import stop_serial_capture_for_device
from app.ws_handlers import (
    broadcast_device_connected,
    broadcast_device_disconnected,
    broadcast_flash_done,
    broadcast_flash_serial_finished,
    broadcast_flash_task_update,
)

internal_bp = Blueprint('internal_bp', __name__)

INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY')


@internal_bp.before_request
def before_request_func():
    api_key = request.headers.get('X-Internal-API-Key')
    if not api_key or api_key != INTERNAL_API_KEY:
        print('[INTERNAL API] Unauthorized access attempt')
        return jsonify(ok=False, error='Unauthorized access to internal API'), 403


@internal_bp.route('/api/internal/hardware/discover', methods=['POST'])
def discover_hardware():
    try:
        data = request.get_json()

        if not data:
            print('[INTERNAL API] No JSON data provided')
            return jsonify(ok=False, error='No data provided'), 400

        port = data.get('port')
        vid = data.get('vendor_id')
        pid = data.get('product_id')
        serial_number = data.get('serial_number')

        if not port:
            print("[INTERNAL API] Missing 'port' in request")
            return jsonify(ok=False, error="Missing 'port' information"), 400

        if not vid or not pid:
            print('[INTERNAL API] Missing vendor_id or product_id')
            return jsonify(ok=False, error="Missing 'vendor_id' or 'product_id' information"), 400

        print(f'[INTERNAL API] Device discovery request: port={port}, vid={vid}, pid={pid}, serial={serial_number}')

        success, message, status_code = hardware_service.handle_device_connect(port, vid, pid, serial_number)

        if success:
            print(f'[INTERNAL API] Device discovery successful: {message}')
            try:
                device = hardware_service.get_device_by_port(port)
                if device:
                    broadcast_device_connected(
                        tag_name=device['tag_name'],
                        port=port,
                        device_type=device.get('type', 'unknown'),
                    )
            except Exception as ws_err:
                print(f'[WS] Failed to broadcast device_connected: {ws_err}')
        else:
            print(f'[INTERNAL API] Device discovery failed: {message}')

        return jsonify(ok=success, message=message), status_code
    except Exception as exc:
        print(f'[INTERNAL API ERROR] Exception in discover_hardware: {exc}')
        traceback.print_exc()
        return jsonify(ok=False, error=f'Internal server error: {str(exc)}'), 500


@internal_bp.route('/api/internal/hardware/disconnect', methods=['POST'])
def disconnect_hardware():
    try:
        data = request.get_json()

        if not data:
            print('[INTERNAL API] No JSON data provided')
            return jsonify(ok=False, error='No data provided'), 400

        port = data.get('port')

        if not port:
            print("[INTERNAL API] Missing 'port' in disconnect request")
            return jsonify(ok=False, error="Missing 'port' information"), 400

        print(f'[INTERNAL API] Device disconnect request: port={port}')

        try:
            device = hardware_service.get_device_by_port(port)
            tag_name_to_broadcast = device['tag_name'] if device else None
        except Exception:
            tag_name_to_broadcast = None

        success, message, status_code = hardware_service.handle_device_disconnect(port)

        if success:
            print(f'[INTERNAL API] Device disconnect successful: {message}')
            if tag_name_to_broadcast:
                stop_serial_capture_for_device(tag_name_to_broadcast)
                failed_requests = flash_queue_service.fail_flashing_requests_for_device(
                    tag_name_to_broadcast,
                    'Device disconnected during flashing or serial capture.',
                )
                for queue_row in failed_requests:
                    broadcast_flash_serial_finished(
                        request_id=queue_row['id'],
                        tag_name=queue_row['tag_name'],
                        user=queue_row['user_id'],
                        reason='device_disconnected',
                    )
                    broadcast_flash_done(
                        tag_name=queue_row['tag_name'],
                        user=queue_row['user_id'],
                        success=False,
                        log='Device disconnected during flashing or serial capture.',
                    )
                    broadcast_flash_task_update(
                        request_id=queue_row['id'],
                        tag_name=queue_row['tag_name'],
                        user=queue_row['user_id'],
                        status='failed',
                        log='Device disconnected during flashing or serial capture.',
                    )
            if tag_name_to_broadcast:
                try:
                    broadcast_device_disconnected(tag_name=tag_name_to_broadcast, port=port)
                except Exception as ws_err:
                    print(f'[WS] Failed to broadcast device_disconnected: {ws_err}')
        else:
            print(f'[INTERNAL API] Device disconnect failed: {message}')

        return jsonify(ok=success, message=message), status_code
    except Exception as exc:
        print(f'[INTERNAL API ERROR] Exception in disconnect_hardware: {exc}')
        traceback.print_exc()
        return jsonify(ok=False, error=f'Internal server error: {str(exc)}'), 500
