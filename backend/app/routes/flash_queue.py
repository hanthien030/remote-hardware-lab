from flask import Blueprint, jsonify, request

from app.auth_decorator import require_auth
from app.logger import log_action
from app.services import flash_queue_service, flash_queue_worker, flash_serial_session

flash_queue_bp = Blueprint('flash_queue_bp', __name__)


@flash_queue_bp.route('/api/flash/devices', methods=['GET'])
@require_auth(role='user')
def get_eligible_devices():
    username = request.current_user['username']
    devices = flash_queue_service.list_eligible_devices(username)
    return jsonify(ok=True, devices=devices)


@flash_queue_bp.route('/api/flash/requests', methods=['POST'])
@require_auth(role='user')
def enqueue_flash_request():
    username = request.current_user['username']
    data = request.get_json() or {}

    project_name = (data.get('project_name') or '').strip()
    tag_name = (data.get('tag_name') or '').strip()
    board_type = (data.get('board_type') or '').strip()
    firmware_path = (data.get('firmware_path') or '').strip()

    if not all([project_name, tag_name, board_type, firmware_path]):
        return jsonify(ok=False, error='Missing required fields: project_name, tag_name, board_type, firmware_path'), 400

    try:
        queued_request = flash_queue_service.enqueue_request(
            username=username,
            project_name=project_name,
            tag_name=tag_name,
            board_type=board_type,
            firmware_path=firmware_path,
        )
        log_action(username, 'Enqueue Flash Request', details={
            'request_id': queued_request['id'],
            'tag_name': tag_name,
            'board_type': board_type,
            'project_name': project_name,
        })
        return jsonify(ok=True, request=queued_request), 201
    except FileNotFoundError as exc:
        return jsonify(ok=False, error=str(exc)), 404
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 409
    except RuntimeError as exc:
        return jsonify(ok=False, error=str(exc)), 503


@flash_queue_bp.route('/api/flash/requests/active', methods=['GET'])
@require_auth(role='user')
def get_active_request():
    username = request.current_user['username']
    active_request = flash_queue_service.get_active_request(username)
    return jsonify(ok=True, request=active_request)


@flash_queue_bp.route('/api/flash/requests', methods=['GET'])
@require_auth(role='user')
def list_flash_history():
    username = request.current_user['username']
    page = request.args.get('page', default=1, type=int)
    limit = request.args.get('limit', default=20, type=int)
    status = request.args.get('status', default=None, type=str)

    history = flash_queue_service.list_history(username, page=page, limit=limit, status=status)
    return jsonify(ok=True, **history)


@flash_queue_bp.route('/api/flash/requests/<int:request_id>', methods=['GET'])
@require_auth(role='user')
def get_flash_request_detail(request_id: int):
    username = request.current_user['username']
    row = flash_queue_service.get_request_detail(username, request_id)
    if not row:
        return jsonify(ok=False, error='Flash request not found'), 404
    return jsonify(ok=True, request=row)


@flash_queue_bp.route('/api/flash/requests/<int:request_id>/cancel', methods=['POST'])
@require_auth(role='user')
def cancel_flash_request(request_id: int):
    username = request.current_user['username']
    row = flash_queue_service.cancel_waiting_request(username, request_id)
    if not row:
        return jsonify(ok=False, error='Only waiting requests can be cancelled'), 409

    log_action(username, 'Cancel Flash Request', details={'request_id': request_id})
    return jsonify(ok=True, request=row)


@flash_queue_bp.route('/api/flash/requests/<int:request_id>/stop-live', methods=['POST'])
@require_auth(role='user')
def stop_live_flash_session(request_id: int):
    username = request.current_user['username']
    row = flash_queue_service.get_request_detail(username, request_id)
    if not row:
        return jsonify(ok=False, error='Flash request not found'), 404
    if row.get('status') != 'flashing':
        return jsonify(ok=False, error='Only active flashing requests can stop the live session'), 409
    if not flash_serial_session.is_session_owned_by(request_id, username):
        return jsonify(ok=False, error='Live serial session is not active for this request'), 409

    flash_serial_session.request_stop(request_id, username)
    flash_queue_worker.stop_serial_capture_for_device(row['tag_name'])
    log_action(username, 'Stop Live Serial Session', details={'request_id': request_id, 'tag_name': row['tag_name']})
    return jsonify(ok=True, request=row)
