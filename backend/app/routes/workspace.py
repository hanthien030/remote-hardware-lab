# file: backend/app/routes/workspace.py
"""
Workspace API — quản lý file code per-user per-device.
Storage: filesystem tại /workspaces/{username}/{project_name}/
"""

import os
import re
import json
import shutil
import requests as http_requests
from flask import Blueprint, request, jsonify, Response, stream_with_context
from app.auth_decorator import require_auth
from app.logger import log_action

workspace_bp = Blueprint('workspace_bp', __name__)

WORKSPACE_ROOT = os.getenv('WORKSPACE_ROOT', '/workspaces')

# Regex để validate tên file an toàn (chống path traversal)
SAFE_PATH_RE = re.compile(r'^[\w\-. /]+$')
SAFE_NAME_RE = re.compile(r'^[\w\-]+$')  # cho username / project_name


def _workspace_path(username: str, project_name: str) -> str:
    """Trả về path thư mục workspace, tạo nếu chưa có."""
    if not SAFE_NAME_RE.match(username) or not SAFE_NAME_RE.match(project_name):
        raise ValueError("Invalid username or project_name")
    path = os.path.join(WORKSPACE_ROOT, username, project_name)
    os.makedirs(path, exist_ok=True)
    return path


def _safe_file_path(username: str, project_name: str, filename: str) -> str:
    """Trả về path tuyệt đối của file, validate chống traversal."""
    if not SAFE_PATH_RE.match(filename):
        raise ValueError(f"Invalid characters in path: {filename}")
    ws = _workspace_path(username, project_name)
    full = os.path.realpath(os.path.join(ws, filename))
    ws_real = os.path.realpath(ws)
    if not full.startswith(ws_real + os.sep):
        raise ValueError("Path traversal detected")
    return full


# ─── PROJECTS SYSTEM (3A-3) ───────────────────────────────────────────────────

@workspace_bp.route('/api/workspace/projects', methods=['GET'])
@require_auth
def list_projects():
    username = request.current_user['username']
    user_ws = os.path.join(WORKSPACE_ROOT, username)
    if not os.path.exists(user_ws):
        return jsonify(ok=True, projects=[])
    
    projects = []
    for d in os.listdir(user_ws):
        if os.path.isdir(os.path.join(user_ws, d)):
            projects.append({'name': d})
            
    return jsonify(ok=True, projects=projects)


@workspace_bp.route('/api/workspace/projects', methods=['POST'])
@require_auth
def create_project():
    username = request.current_user['username']
    data = request.get_json()
    project_name = (data or {}).get('project_name', '').strip()
    
    if not SAFE_NAME_RE.match(project_name):
        return jsonify(ok=False, error="Invalid project name (alphanumeric and dashes only)"), 400
        
    try:
        ws_path = _workspace_path(username, project_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400
        
    # Check if we just created it (by ensuring main.cpp is dropped if new)
    # The _workspace_path already does os.makedirs(exist_ok=True)
    # Let's drop a default main.cpp
    main_path = os.path.join(ws_path, 'main.cpp')
    if not os.path.exists(main_path):
        default_code = (
            "// Remote Lab — ESP32 Firmware\n"
            "// Project: " + project_name + "\n\n"
            "void setup() {\n"
            "  Serial.begin(115200);\n"
            "  Serial.println(\"Hello from Remote Lab!\");\n"
            "}\n\n"
            "void loop() {\n"
            "  // Your code here\n"
            "  delay(1000);\n"
            "}\n"
        )
        with open(main_path, 'w') as f:
            f.write(default_code)
            
    log_action(username, 'Create Project', details={'project': project_name})
    return jsonify(ok=True, project={'name': project_name}), 201


@workspace_bp.route('/api/workspace/projects/<string:project_name>', methods=['DELETE'])
@require_auth
def delete_project(project_name: str):
    username = request.current_user['username']
    if not SAFE_NAME_RE.match(project_name):
        return jsonify(ok=False, error="Invalid project name"), 400
        
    ws_path = os.path.join(WORKSPACE_ROOT, username, project_name)
    if not os.path.exists(ws_path):
        return jsonify(ok=False, error="Project not found"), 404
        
    shutil.rmtree(ws_path)
    log_action(username, 'Delete Project', details={'project': project_name})
    return jsonify(ok=True, message=f"Deleted project {project_name}")


# ─── FILES & FOLDERS ──────────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files', methods=['GET'])
@require_auth
def list_files(project_name: str):
    username = request.current_user['username']
    try:
        ws = _workspace_path(username, project_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    files = []
    has_main_cpp = False
    
    for root, dirs, filenames in os.walk(ws):
        rel_root = os.path.relpath(root, ws)
        if rel_root == '.':
            rel_root = ''
            
        for d in dirs:
            fpath = os.path.join(root, d)
            rel_path = os.path.join(rel_root, d).replace('\\', '/')
            stat = os.stat(fpath)
            files.append({
                'filename': rel_path,
                'type': 'folder',
                'updated_at': stat.st_mtime
            })
            
        for f in filenames:
            fpath = os.path.join(root, f)
            rel_path = os.path.join(rel_root, f).replace('\\', '/')
            stat = os.stat(fpath)
            files.append({
                'filename': rel_path,
                'type': 'file',
                'size_bytes': stat.st_size,
                'updated_at': stat.st_mtime
            })
            if rel_path == 'main.cpp':
                has_main_cpp = True

    # Nếu workspace chưa có main.cpp (thường là mới tinh mà chưa sinh), tạo file main.cpp mặc định
    if not has_main_cpp and len(files) == 0:
        default_code = (
            "// Remote Lab — ESP32 Firmware\n"
            "// Device: " + project_name + "\n\n"
            "void setup() {\n"
            "  Serial.begin(115200);\n"
            "  Serial.println(\"Hello from Remote Lab!\");\n"
            "}\n\n"
            "void loop() {\n"
            "  // Your code here\n"
            "  delay(1000);\n"
            "}\n"
        )
        main_path = os.path.join(ws, 'main.cpp')
        with open(main_path, 'w') as f:
            f.write(default_code)
        files = [{'filename': 'main.cpp', 'size_bytes': len(default_code), 'updated_at': os.stat(main_path).st_mtime}]

    return jsonify(ok=True, files=files, workspace=f"{username}/{project_name}")


# ─── READ FILE ────────────────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files/<path:filename>', methods=['GET'])
@require_auth
def read_file(project_name: str, filename: str):
    username = request.current_user['username']
    try:
        fpath = _safe_file_path(username, project_name, filename)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if not os.path.exists(fpath):
        return jsonify(ok=False, error="File not found"), 404

    with open(fpath, 'r', errors='replace') as f:
        content = f.read()

    return jsonify(ok=True, filename=filename, content=content)


# ─── SAVE / UPDATE FILE ───────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files/<path:filename>', methods=['PUT'])
@require_auth
def save_file(project_name: str, filename: str):
    username = request.current_user['username']
    data = request.get_json()
    if data is None or 'content' not in data:
        return jsonify(ok=False, error="Missing 'content' field"), 400

    content = data['content']
    if len(content) > 512 * 1024:  # 512KB limit per file
        return jsonify(ok=False, error="File too large (max 512KB)"), 413

    try:
        fpath = _safe_file_path(username, project_name, filename)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    with open(fpath, 'w') as f:
        f.write(content)

    return jsonify(ok=True, filename=filename, size_bytes=len(content.encode()))


# ─── CREATE FILE ──────────────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files', methods=['POST'])
@require_auth
def create_file(project_name: str):
    username = request.current_user['username']
    data = request.get_json()
    filename = (data or {}).get('filename', '').strip()
    content = (data or {}).get('content', '')

    try:
        fpath = _safe_file_path(username, project_name, filename)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if os.path.exists(fpath):
        return jsonify(ok=False, error=f"File '{filename}' already exists"), 409

    with open(fpath, 'w') as f:
        f.write(content)

    log_action(username, 'Create Workspace File', details={'project': project_name, 'file': filename})
    return jsonify(ok=True, filename=filename), 201


# ─── CREATE FOLDER ────────────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/folders', methods=['POST'])
@require_auth
def create_folder(project_name: str):
    username = request.current_user['username']
    data = request.get_json()
    folder_path = (data or {}).get('folder_path', '').strip()

    if not folder_path:
        return jsonify(ok=False, error="Missing folder_path"), 400

    try:
        fpath = _safe_file_path(username, project_name, folder_path)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if os.path.exists(fpath):
        return jsonify(ok=False, error=f"Folder or file '{folder_path}' already exists"), 409

    os.makedirs(fpath, exist_ok=True)
    log_action(username, 'Create Workspace Folder', details={'project': project_name, 'folder': folder_path})
    return jsonify(ok=True, folder_path=folder_path), 201


# ─── DELETE FILE OR FOLDER ─────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files/<path:filename>', methods=['DELETE'])
@require_auth
def delete_file(project_name: str, filename: str):
    username = request.current_user['username']
    try:
        fpath = _safe_file_path(username, project_name, filename)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if not os.path.exists(fpath):
        return jsonify(ok=False, error="Not found"), 404

    if os.path.isdir(fpath):
        shutil.rmtree(fpath)
    else:
        os.remove(fpath)
        
    log_action(username, 'Delete Item', details={'project': project_name, 'item': filename})
    return jsonify(ok=True, message=f"Deleted {filename}")


# ─── RENAME ITEM (FILE/FOLDER) ──────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files/<path:filename>/rename', methods=['PATCH'])
@require_auth
def rename_file(project_name: str, filename: str):
    username = request.current_user['username']
    data = request.get_json()
    new_name = (data or {}).get('new_filename', '').strip()

    try:
        old_path = _safe_file_path(username, project_name, filename)
        new_path = _safe_file_path(username, project_name, new_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if not os.path.exists(old_path):
        return jsonify(ok=False, error="Item not found"), 404
    if os.path.exists(new_path):
        return jsonify(ok=False, error=f"'{new_name}' already exists"), 409
        
    # Create parent directories for the new path if moving
    os.makedirs(os.path.dirname(new_path), exist_ok=True)

    os.rename(old_path, new_path)
    log_action(username, 'Rename/Move Item', details={'project': project_name, 'from': filename, 'to': new_name})
    return jsonify(ok=True, old_filename=filename, new_filename=new_name)


# ─── COPY ITEM (FILE/FOLDER) ────────────────────────────────────────────────────
@workspace_bp.route('/api/workspace/<string:project_name>/files/<path:filename>/copy', methods=['POST'])
@require_auth
def copy_file(project_name: str, filename: str):
    username = request.current_user['username']
    data = request.get_json()
    new_name = (data or {}).get('new_filename', '').strip()

    try:
        old_path = _safe_file_path(username, project_name, filename)
        new_path = _safe_file_path(username, project_name, new_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    if not os.path.exists(old_path):
        return jsonify(ok=False, error="Item not found"), 404
    if os.path.exists(new_path):
        return jsonify(ok=False, error=f"'{new_name}' already exists"), 409
        
    os.makedirs(os.path.dirname(new_path), exist_ok=True)

    if os.path.isdir(old_path):
        import shutil
        shutil.copytree(old_path, new_path)
    else:
        import shutil
        shutil.copy2(old_path, new_path)
        
    log_action(username, 'Copy Item', details={'project': project_name, 'from': filename, 'to': new_name})
    return jsonify(ok=True, old_filename=filename, new_filename=new_name)


# ─── COMPILE (3B-3) ─────────────────────────────────────────────────────────────

COMPILER_URL = os.getenv('COMPILER_URL', 'http://compiler:9000')
SUPPORTED_EXTS = {'.cpp', '.c', '.h', '.hpp', '.ino', '.py', '.json', '.txt', '.md'}

@workspace_bp.route('/api/workspace/<string:project_name>/compile', methods=['POST'])
@require_auth
def compile_project(project_name: str):
    """
    SSE stream compile log from compiler service.
    Body: {"board": "esp32"}   (optional, default esp32)
    Proxies to compiler service /compile-stream, streams back to client.
    On success: saves the board-specific firmware artifact into /workspaces/{user}/{project}/build/
    """
    username = request.current_user['username']
    data = request.get_json() or {}
    board = data.get('board', 'esp32')

    # Collect all source files from workspace
    try:
        ws_path = _workspace_path(username, project_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400

    files = {}
    for root, dirs, fnames in os.walk(ws_path):
        # Skip build output dir
        dirs[:] = [d for d in dirs if d != 'build']
        for fname in fnames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_EXTS:
                rel = os.path.relpath(os.path.join(root, fname), ws_path)
                with open(os.path.join(root, fname), 'r', encoding='utf-8', errors='replace') as f:
                    files[rel] = f.read()

    if not files:
        return jsonify(ok=False, error='No source files found in project'), 400

    build_dir = os.path.join(ws_path, 'build')

    def _proxy_stream():
        try:
            resp = http_requests.post(
                f'{COMPILER_URL}/compile-stream',
                json={'files': files, 'board': board},
                stream=True,
                timeout=300
            )

            artifact_b64 = None
            artifact_filename = None
            artifact_ext = None
            flash_tool_hint = None
            flash_layout = None

            for chunk in resp.iter_lines(chunk_size=None):
                if not chunk:
                    yield '\n\n'
                    continue

                line = chunk if isinstance(chunk, str) else chunk.decode('utf-8')
                yield line + '\n\n'

                # Parse the compiler completion event and persist the saved artifact after the stream closes.
                if line.startswith('data: '):
                    try:
                        evt = json.loads(line[6:])
                        if evt.get('stage') == 'done':
                            artifact_b64 = evt.get('artifact_base64') or evt.get('bin_base64')
                            artifact_filename = evt.get('artifact_filename') or evt.get('bin_filename')
                            artifact_ext = evt.get('artifact_ext')
                            flash_tool_hint = evt.get('flash_tool_hint')
                            flash_layout = evt.get('flash_layout')
                    except Exception:
                        pass

            # After stream ends — save the board-specific firmware artifact to the workspace.
            if artifact_b64 and artifact_filename:
                import base64
                os.makedirs(build_dir, exist_ok=True)
                # Clean old artifacts first
                import glob
                for old in glob.glob(os.path.join(build_dir, '*.bin')):
                    os.remove(old)
                for old in glob.glob(os.path.join(build_dir, '*.hex')):
                    os.remove(old)
                for old in glob.glob(os.path.join(build_dir, '*.flash.json')):
                    os.remove(old)
                artifact_basename = os.path.basename(artifact_filename)
                artifact_path = os.path.join(build_dir, artifact_basename)
                with open(artifact_path, 'wb') as artifact_file:
                    artifact_file.write(base64.b64decode(artifact_b64))

                manifest_rel = None
                if flash_layout and isinstance(flash_layout.get('segments'), list):
                    manifest_segments = []
                    for segment in flash_layout['segments']:
                        segment_filename = os.path.basename(segment.get('filename', ''))
                        segment_offset = segment.get('offset')
                        if not segment_filename or not segment_offset:
                            continue

                        if segment_filename == artifact_basename:
                            segment_path = artifact_path
                        else:
                            segment_b64 = segment.get('base64')
                            if not segment_b64:
                                continue
                            segment_path = os.path.join(build_dir, segment_filename)
                            with open(segment_path, 'wb') as sf:
                                sf.write(base64.b64decode(segment_b64))

                        manifest_segments.append({
                            'offset': segment_offset,
                            'path': f'build/{os.path.basename(segment_path)}',
                        })

                    if manifest_segments:
                        manifest_filename = f'{os.path.splitext(artifact_basename)[0]}.flash.json'
                        manifest_path = os.path.join(build_dir, manifest_filename)
                        with open(manifest_path, 'w', encoding='utf-8') as mf:
                            json.dump({
                                'tool': flash_layout.get('tool', 'esptool.py'),
                                'board': board,
                                'flash_mode': flash_layout.get('flash_mode'),
                                'flash_freq': flash_layout.get('flash_freq'),
                                'flash_size': flash_layout.get('flash_size'),
                                'segments': manifest_segments,
                            }, mf, indent=2)
                        manifest_rel = f'build/{manifest_filename}'

                # Emit final marker for frontend
                saved_rel = f'build/{artifact_basename}'
                saved_evt = json.dumps({
                    'stage': 'saved',
                    'path': saved_rel,
                    'artifact_ext': artifact_ext or os.path.splitext(saved_rel)[1].lower(),
                    'flash_tool_hint': flash_tool_hint,
                    'log': f'Firmware artifact saved to {saved_rel}',
                })
                yield f'data: {saved_evt}\n\n'
                log_action(username, 'Compile Project',
                           details={
                               'project': project_name,
                               'board': board,
                               'artifact': saved_rel,
                               'artifact_ext': artifact_ext or os.path.splitext(saved_rel)[1].lower(),
                               'flash_tool_hint': flash_tool_hint,
                               'flash_manifest': manifest_rel,
                           })

        except http_requests.exceptions.ConnectionError:
            err = json.dumps({'stage': 'error', 'error': 'Cannot reach compiler service'})
            yield f'data: {err}\n\n'
        except Exception as e:
            err = json.dumps({'stage': 'error', 'error': str(e)})
            yield f'data: {err}\n\n'

    return Response(
        stream_with_context(_proxy_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )
