# file: backend/app/routes/hardware.py

import os
import json
import requests
from flask import Blueprint, jsonify, session, request, Response, stream_with_context
from app.services import hardware_service
from app.auth_decorator import require_auth
from app.logger import log_action
from app.ws_handlers import (
    broadcast_device_locked,
    broadcast_device_unlocked,
    broadcast_flash_started,
    broadcast_flash_done,
)

hw_bp = Blueprint('hw_bp', __name__)

# Service URLs
BROKER_URL = os.getenv("BROKER_URL", "http://broker:8000")
COMPILER_URL = os.getenv("COMPILER_URL", "http://compiler:9000")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", "/workspaces")

@hw_bp.route('/api/hardware/my-devices', methods=['GET'])
@require_auth(role='user')
def get_my_devices():
    username = session['username']
    assignments = hardware_service.get_user_assignments(username)
    return jsonify(ok=True, devices=assignments)

@hw_bp.route('/api/hardware/flash', methods=['POST'])
@require_auth(role='user')
def flash_device():
    username = session['username']
    data = request.get_json()
    tag_name = data.get('tag_name')
    slot_id = data.get('slot_id')
    firmware_base64 = data.get('firmware_base64')

    if not tag_name or not firmware_base64:
        return jsonify(ok=False, error="Missing required fields: tag_name, firmware_base64"), 400

    # 1. Kiểm tra quyền của người dùng
    user_assignments = hardware_service.get_user_assignments(username)
    if not any(d['tag_name'] == tag_name for d in user_assignments):
        log_action(username, 'Flash Attempt Failed', success=False, details={'reason': 'Permission denied', 'tag': tag_name})
        return jsonify(ok=False, error="Permission denied for this device"), 403

    # 2. Lấy thông tin port của thiết bị
    device = hardware_service.get_device_by_tag(tag_name)
    if not device:
        return jsonify(ok=False, error="Device not found"), 404
    if device['status'] != 'connected':
        return jsonify(ok=False, error="Device is not connected"), 409
    
    # === THÊM LOGIC KIỂM TRA LOCK ===
    if bool(device['is_virtualized']):
        # Nếu là thiết bị ảo hóa, BẮT BUỘC phải có slot_id
        if slot_id is None:
            return jsonify(ok=False, error="Missing required field: slot_id for virtualized device"), 400
    else:
        # Nếu là thiết bị thường, phải được khóa bởi người dùng
        if device['locked_by_user'] != username:
            return jsonify(ok=False, error="Device is not locked by you. Please lock it first."), 403
        
    # 3. Chuyển tiếp yêu cầu đến Broker
    try:
        broker_payload = {
            "port": device['port'],
            "slot_id": slot_id,
            "firmware_base64": firmware_base64,
            "is_virtualized": bool(device['is_virtualized'])
        }
        broker_endpoint = f"{BROKER_URL}/flash-firmware"
        
        response = requests.post(broker_endpoint, json=broker_payload, timeout=120) 
        
        # Nếu broker trả lỗi, forward lại nguyên văn error message của broker (bao gồm stderr esptool)
        if not response.ok:
            try:
                broker_err = response.json()
                err_msg = broker_err.get('detail') or broker_err.get('error') or response.text
            except Exception:
                err_msg = response.text
            log_action(username, 'Flash Attempt Failed', success=False, details={'reason': 'Broker error', 'error': err_msg})
            return jsonify(ok=False, error=err_msg), response.status_code

        log_action(username, 'Flash Device', success=True, details={'tag': tag_name, 'slot': slot_id})
        return response.json(), response.status_code

    except requests.exceptions.RequestException as e:
        log_action(username, 'Flash Attempt Failed', success=False, details={'reason': 'Broker connection error', 'error': str(e)})
        return jsonify(ok=False, error=f"Failed to communicate with Broker: {e}"), 502
    
@hw_bp.route('/api/hardware/lock/<string:tag_name>', methods=['POST'])
@require_auth(role='user')
def lock(tag_name):
    username = session['username']
    # Kiểm tra quyền
    user_assignments = hardware_service.get_user_assignments(username)
    if not any(d['tag_name'] == tag_name for d in user_assignments):
        return jsonify(ok=False, error="Permission denied"), 403

    success, message = hardware_service.lock_device(tag_name, username)
    if success:
        try:
            broadcast_device_locked(tag_name=tag_name, locked_by=username)
        except Exception:
            pass
        return jsonify(ok=True, message=message)
    else:
        return jsonify(ok=False, error=message), 409

@hw_bp.route('/api/hardware/unlock/<string:tag_name>', methods=['POST'])
@require_auth(role='user')
def unlock(tag_name):
    username = session['username']
    success, message = hardware_service.unlock_device(tag_name, username)
    if success:
        try:
            broadcast_device_unlocked(tag_name=tag_name)
        except Exception:
            pass
        return jsonify(ok=True, message=message)
    else:
        return jsonify(ok=False, error=message), 403


# ─── COMPILE-FLASH SSE STREAM ─────────────────────────────────────────────────

def _sse(data: dict) -> str:
    """Format dict as SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@hw_bp.route('/api/hardware/compile-flash', methods=['GET'])
@require_auth
def compile_flash_stream():
    """
    SSE endpoint: Compile C++ code từ workspace → flash lên thiết bị.
    Query params: tag_name, filename (default: main.cpp), board (default: esp32)
    
    Stream events:
      {"stage": "compile", "log": "..."}
      {"stage": "flash",   "log": "..."}
      {"stage": "done",    "ok": true, "bytes_written": 123456}
      {"stage": "error",   "error": "..."}
    """
    username = request.current_user['username']
    tag_name = request.args.get('tag_name', '').strip()
    project_name = request.args.get('project_name', tag_name).strip()
    filename = request.args.get('filename', 'main.cpp').strip()
    board = request.args.get('board', 'esp32').strip()

    def generate():
        # ── Step 1: Validate quyền ──────────────────────────
        user_assignments = hardware_service.get_user_assignments(username)
        if not any(d['tag_name'] == tag_name for d in user_assignments):
            yield _sse({"stage": "error", "error": "Permission denied for this device"})
            return

        device = hardware_service.get_device_by_tag(tag_name)
        if not device:
            yield _sse({"stage": "error", "error": "Device not found"})
            return
        if device['status'] != 'connected':
            yield _sse({"stage": "error", "error": "Device is not connected"})
            return
        if not device['is_virtualized'] and device['locked_by_user'] != username:
            yield _sse({"stage": "error", "error": "Device must be locked by you before flashing"})
            return

        # ── Step 2: Đọc code từ workspace ───────────────────
        import re
        safe_re = re.compile(r'^[\w\-]+$')
        if not safe_re.match(username) or not safe_re.match(project_name):
            yield _sse({"stage": "error", "error": "Invalid path"})
            return

        workspace_path = os.path.join(WORKSPACE_ROOT, username, project_name, filename)
        if not os.path.isfile(workspace_path):
            yield _sse({"stage": "error", "error": f"File '{filename}' not found in project '{project_name}'"})
            return

        with open(workspace_path, 'r') as f:
            code = f.read()

        yield _sse({"stage": "compile", "log": f"📂 Reading {filename} ({len(code)} bytes)..."})

        # ── Step 3: Gọi Compiler ────────────────────────────
        yield _sse({"stage": "compile", "log": f"🔨 Compiling for board '{board}'..."})
        try:
            compiler_resp = requests.post(
                f"{COMPILER_URL}/compile",
                json={"code": code, "board": board},
                timeout=200
            )
        except requests.exceptions.RequestException as e:
            yield _sse({"stage": "error", "error": f"Cannot reach compiler service: {e}"})
            return

        comp_data = compiler_resp.json()
        compile_log = comp_data.get("compile_log", "")

        # Stream từng dòng log compile
        for line in compile_log.strip().splitlines():
            if line.strip():
                yield _sse({"stage": "compile", "log": line})

        if not comp_data.get("ok"):
            err = comp_data.get("error", "Compilation failed")
            yield _sse({"stage": "error", "error": err})
            log_action(username, 'Compile Failed', success=False, details={'tag': tag_name, 'file': filename, 'error': err})
            return

        bin_base64 = comp_data["bin_base64"]
        size_bytes = comp_data.get("size_bytes", 0)
        yield _sse({"stage": "compile", "log": f"✅ Compiled! Binary size: {size_bytes:,} bytes"})

        # ── Step 4: Flash qua Broker ────────────────────────
        yield _sse({"stage": "flash", "log": "⚡ Starting flash sequence..."})
        try:
            broker_payload = {
                "port": device['port'],
                "firmware_base64": bin_base64,
                "is_virtualized": bool(device['is_virtualized']),
                "slot_id": None,
            }
            broker_resp = requests.post(
                f"{BROKER_URL}/flash-firmware",
                json=broker_payload,
                timeout=150
            )
        except requests.exceptions.RequestException as e:
            yield _sse({"stage": "error", "error": f"Broker connection failed: {e}"})
            return

        if not broker_resp.ok:
            try:
                broker_err = broker_resp.json()
                err_msg = broker_err.get('detail') or broker_err.get('error') or broker_resp.text
            except Exception:
                err_msg = broker_resp.text
            yield _sse({"stage": "error", "error": f"Flash failed: {err_msg}"})
            log_action(username, 'Flash Failed', success=False, details={'tag': tag_name, 'error': err_msg})
            return

        flash_data = broker_resp.json()
        yield _sse({"stage": "flash", "log": f"✅ Flashed {flash_data.get('bytes_written', size_bytes):,} bytes to {device['port']}"})
        yield _sse({"stage": "flash", "log": "🔄 Device resetting..."})
        yield _sse({"stage": "done", "ok": True, "bytes_written": flash_data.get('bytes_written', size_bytes)})

        log_action(username, 'Compile & Flash', success=True,
                   details={'tag': tag_name, 'file': filename, 'board': board, 'bytes': size_bytes})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )