# file: backend/app/routes/admin_hardware.py

from flask import Blueprint, request, jsonify, session
from app.services import hardware_service
from app.logger import log_action
import jwt
import os

admin_hw_bp = Blueprint('admin_hw_bp', __name__)
SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')


@admin_hw_bp.before_request
def before_request_func():
    if request.method == 'OPTIONS':
        return jsonify(ok=True), 200

    username = None
    role = None

    auth_header = request.headers.get('Authorization')
    if auth_header:
        try:
            parts = auth_header.split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
                payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
                username = payload.get('username')
                role = payload.get('role')
        except jwt.ExpiredSignatureError:
            return jsonify(ok=False, error="Token háº¿t háº¡n"), 401
        except jwt.InvalidTokenError:
            return jsonify(ok=False, error="Token khÃ´ng há»£p lá»‡"), 401

    if not username:
        username = session.get('username')
        role = session.get('role')

    if not username or not role:
        return jsonify(ok=False, error="YÃªu cáº§u Ä‘Äƒng nháº­p"), 401

    if role != 'admin':
        return jsonify(ok=False, error="Admin access required"), 403

    session['username'] = username
    session['role'] = role


@admin_hw_bp.route('/api/admin/devices', methods=['GET', 'OPTIONS'])
def get_devices():
    from app.db import get_db_connection

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT d.tag_name, d.device_name, d.type, d.port, d.status, d.usage_mode, d.board_class, d.review_state, d.is_virtualized,
                   d.locked_by_user, d.last_seen, d.created_at,
                   GROUP_CONCAT(a.user_id ORDER BY a.created_at DESC SEPARATOR ', ') AS assigned_to
            FROM devices d
            LEFT JOIN assignments a ON d.tag_name = a.tag_name
                AND a.is_active = TRUE AND (a.expires_at IS NULL OR a.expires_at > NOW())
            WHERE d.review_state = 'approved'
            GROUP BY d.tag_name
            ORDER BY d.created_at DESC
            """
        )
        devices = cursor.fetchall()

        cursor.execute(
            """
            SELECT tag_name, user_id, expires_at
            FROM assignments
            WHERE is_active = TRUE AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC
            """
        )
        assignment_rows = cursor.fetchall()

        assignments_by_tag = {}
        for row in assignment_rows:
            assignments_by_tag.setdefault(row['tag_name'], []).append({
                'user_id': row['user_id'],
                'expires_at': row['expires_at'].isoformat() if row.get('expires_at') else None,
            })

        for device in devices:
            device['usage_mode'] = device.get('usage_mode') or 'free'
            device['assignments'] = assignments_by_tag.get(device['tag_name'], [])

        return jsonify(ok=True, devices=devices)
    finally:
        cursor.close()


@admin_hw_bp.route('/api/admin/devices/pending', methods=['GET', 'OPTIONS'])
def get_pending_devices():
    from app.db import get_db_connection

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT tag_name, device_name, type, port, status, usage_mode,
                   board_class, review_state, chip_type, chip_family,
                   mac_address, flash_size, crystal_freq, created_at, last_seen
            FROM devices
            WHERE review_state = 'pending_review'
            ORDER BY created_at DESC, tag_name ASC
            """
        )
        return jsonify(ok=True, devices=cursor.fetchall())
    finally:
        cursor.close()


@admin_hw_bp.route('/api/admin/assignments/<string:tag_name>', methods=['DELETE', 'OPTIONS'])
def revoke_assignment(tag_name):
    from app.db import get_db_connection

    data = request.get_json() or {}
    user_id = data.get('user_id')

    db = get_db_connection()
    cursor = db.cursor()
    try:
        if user_id:
            cursor.execute(
                "UPDATE assignments SET is_active = FALSE WHERE tag_name = %s AND user_id = %s",
                (tag_name, user_id)
            )
        else:
            cursor.execute(
                "UPDATE assignments SET is_active = FALSE WHERE tag_name = %s AND is_active = TRUE",
                (tag_name,)
            )
        db.commit()
        admin_username = session.get('username', 'admin')
        log_action(admin_username, 'Revoke Assignment', details={'tag': tag_name, 'user': user_id or 'all'})
        return jsonify(ok=True, message="Assignment revoked successfully.")
    except Exception as e:
        db.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        cursor.close()


@admin_hw_bp.route('/api/admin/devices/<string:tag_name>', methods=['PUT', 'OPTIONS'])
def update_device(tag_name):
    from app.db import get_db_connection

    data = request.get_json() or {}
    new_tag_name = data.get('tag_name')
    new_device_name = data.get('device_name')
    usage_mode = data.get('usage_mode')

    if usage_mode is not None and usage_mode not in ('free', 'share', 'block'):
        return jsonify(ok=False, error="Invalid usage_mode"), 400

    if not new_tag_name:
        return jsonify(ok=False, error="Missing new tag_name in request body"), 400

    existing_device = hardware_service.get_device_by_tag(tag_name)
    if not existing_device:
        return jsonify(ok=False, error=f"No device found with tag_name: {tag_name}"), 404

    identity_changed = (
        new_tag_name != existing_device.get('tag_name')
        or (new_device_name != existing_device.get('device_name'))
    )

    if identity_changed:
        success, message = hardware_service.update_device_info(tag_name, new_tag_name, new_device_name)
        if not success:
            if "No device found" in message:
                return jsonify(ok=False, error=message), 404
            return jsonify(ok=False, error=message), 500
    else:
        message = "Device updated successfully."

    if usage_mode is not None:
        db = get_db_connection()
        usage_cursor = db.cursor()
        try:
            usage_cursor.execute(
                "UPDATE devices SET usage_mode = %s WHERE tag_name = %s",
                (usage_mode, new_tag_name),
            )
            db.commit()
        except Exception as e:
            db.rollback()
            return jsonify(ok=False, error=str(e)), 500
        finally:
            usage_cursor.close()

    log_action(
        session['username'],
        'Update Device',
        details={'old_tag': tag_name, 'new_tag': new_tag_name, 'usage_mode': usage_mode},
    )
    return jsonify(ok=True, message=message)


@admin_hw_bp.route('/api/admin/devices/<string:tag_name>/approve', methods=['POST', 'OPTIONS'])
def approve_device(tag_name):
    from app.db import get_db_connection

    data = request.get_json() or {}
    device_name = (data.get('device_name') or '').strip() or None
    board_class = (data.get('board_class') or '').strip()

    if board_class not in ('esp32', 'esp8266', 'arduino_uno'):
        return jsonify(ok=False, error="Invalid board_class"), 400

    existing_device = hardware_service.get_device_by_tag(tag_name)
    if not existing_device:
        return jsonify(ok=False, error=f"No device found with tag_name: {tag_name}"), 404
    if existing_device.get('review_state') != 'pending_review':
        return jsonify(ok=False, error="Device is not pending review"), 409

    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute(
            """
            UPDATE devices
            SET device_name = %s,
                board_class = %s,
                review_state = 'approved'
            WHERE tag_name = %s AND review_state = 'pending_review'
            """,
            (device_name, board_class, tag_name),
        )
        if cursor.rowcount != 1:
            db.rollback()
            return jsonify(ok=False, error="Device approval failed"), 409
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify(ok=False, error=str(e)), 500
    finally:
        cursor.close()

    log_action(
        session['username'],
        'Approve Device Review',
        details={'tag_name': tag_name, 'device_name': device_name, 'board_class': board_class},
    )
    return jsonify(ok=True, message='Device approved successfully.')


@admin_hw_bp.route('/api/admin/assignments', methods=['POST', 'OPTIONS'])
def assign_device():
    data = request.get_json()
    user_id = data.get('user_id')
    tag_name = data.get('tag_name')
    expires_at = data.get('expires_at')

    if not all([user_id, tag_name, expires_at]):
        return jsonify(ok=False, error="Missing required fields"), 400

    admin_username = session['username']
    success, message = hardware_service.create_assignment(user_id, tag_name, expires_at, admin_username)

    if success:
        log_action(admin_username, 'Assign Device', details={'user': user_id, 'tag': tag_name, 'expires': expires_at})
        return jsonify(ok=True, message=message), 201
    return jsonify(ok=False, error=message), 500


@admin_hw_bp.route('/api/admin/users', methods=['GET', 'OPTIONS'])
def get_users():
    from app.services import user_service

    try:
        users = user_service.get_all_users()
        return jsonify(ok=True, users=users)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@admin_hw_bp.route('/api/admin/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
def manage_user(user_id):
    from app.services import user_service

    try:
        if request.method == 'GET':
            user = user_service.get_user_by_id(user_id)
            if user:
                return jsonify(ok=True, user=user)
            return jsonify(ok=False, error="User not found"), 404

        if request.method == 'PUT':
            data = request.get_json()
            success, message = user_service.update_user_info(user_id, data)
            if success:
                log_action(session['username'], 'Update User', details={'user_id': user_id})
                return jsonify(ok=True, message=message)
            return jsonify(ok=False, error=message), 400

        if request.method == 'DELETE':
            current_user = session.get('username')
            target_user = user_service.get_user_by_id(user_id)

            if not target_user:
                return jsonify(ok=False, error="User not found"), 404

            if target_user.get('username') == current_user:
                return jsonify(ok=False, error="Cannot delete yourself"), 400

            success, message = user_service.delete_user(user_id)
            if success:
                log_action(current_user, 'Delete User', details={'user_id': user_id, 'username': target_user.get('username')})
                return jsonify(ok=True, message=message), 200
            return jsonify(ok=False, error=message), 400

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500
