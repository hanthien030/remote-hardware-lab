import os
import re
from typing import Dict, List, Optional, Tuple

from app.db import create_db_connection

WORKSPACE_ROOT = os.getenv('WORKSPACE_ROOT', '/workspaces')
SAFE_NAME_RE = re.compile(r'^[\w\-]+$')
SAFE_PATH_RE = re.compile(r'^[\w\-. /]+$')
SUPPORTED_BOARDS = {'esp32', 'esp8266', 'arduino_uno'}
ACTIVE_STATUSES = ('waiting', 'flashing')
USAGE_MODES = {'free', 'share', 'block'}


def _dict_cursor(conn):
    return conn.cursor(dictionary=True)


def _normalize_usage_mode(value: Optional[str]) -> str:
    if value in USAGE_MODES:
        return value
    return 'free'


def _serialize_request(row: Optional[Dict]) -> Optional[Dict]:
    if not row:
        return None

    payload = dict(row)
    payload['project_name'] = _derive_project_name(payload['user_id'], payload['firmware_path'])
    payload['firmware_name'] = os.path.basename(payload['firmware_path'])
    return payload


def _derive_project_name(username: str, firmware_path: str) -> Optional[str]:
    workspace_prefix = os.path.realpath(os.path.join(WORKSPACE_ROOT, username))
    full_path = os.path.realpath(firmware_path)
    if not full_path.startswith(workspace_prefix + os.sep):
        return None

    relative = os.path.relpath(full_path, workspace_prefix)
    parts = relative.split(os.sep)
    return parts[0] if parts else None


def _safe_workspace_file(username: str, project_name: str, firmware_path: str) -> str:
    if not SAFE_NAME_RE.match(username) or not SAFE_NAME_RE.match(project_name):
        raise ValueError('Invalid username or project_name')
    if not SAFE_PATH_RE.match(firmware_path):
        raise ValueError('Invalid firmware path')

    workspace_dir = os.path.realpath(os.path.join(WORKSPACE_ROOT, username, project_name))
    full_path = os.path.realpath(os.path.join(workspace_dir, firmware_path))

    if not full_path.startswith(workspace_dir + os.sep):
        raise ValueError('Path traversal detected')
    if not full_path.lower().endswith('.bin'):
        raise ValueError('Firmware path must point to a .bin file')
    if not os.path.isfile(full_path):
        raise FileNotFoundError('Compiled firmware .bin file not found')

    return full_path


def _advisory_lock_name(username: str) -> str:
    return f'flash_queue_user_{username}'


def _acquire_user_lock(conn, username: str, timeout_seconds: int = 5) -> bool:
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT GET_LOCK(%s, %s) AS lock_acquired', (_advisory_lock_name(username), timeout_seconds))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    finally:
        cursor.close()


def _release_user_lock(conn, username: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT RELEASE_LOCK(%s)', (_advisory_lock_name(username),))
    finally:
        cursor.close()


def _get_user_accessible_devices(conn, username: str) -> List[Dict]:
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT DISTINCT
                   d.tag_name,
                   d.type,
                   d.device_name,
                   d.port,
                   d.status,
                   COALESCE(d.usage_mode, 'free') AS usage_mode,
                   d.locked_by_user,
                   d.is_virtualized,
                   d.total_slots,
                   a.expires_at,
                   CASE WHEN a.user_id IS NULL THEN FALSE ELSE TRUE END AS is_assigned
            FROM devices d
            LEFT JOIN assignments a
              ON a.tag_name = d.tag_name
             AND a.user_id = %s
             AND a.is_active = TRUE
             AND a.expires_at > NOW()
            WHERE COALESCE(d.usage_mode, 'free') = 'free'
               OR (
                    COALESCE(d.usage_mode, 'free') = 'share'
                    AND a.user_id IS NOT NULL
                  )
            ORDER BY d.tag_name ASC
            """,
            (username,),
        )
        devices = cursor.fetchall()
        for device in devices:
            device['usage_mode'] = _normalize_usage_mode(device.get('usage_mode'))
        return devices
    finally:
        cursor.close()


def _get_device_by_tag(conn, tag_name: str) -> Optional[Dict]:
    cursor = _dict_cursor(conn)
    try:
        cursor.execute('SELECT * FROM devices WHERE tag_name = %s', (tag_name,))
        return cursor.fetchone()
    finally:
        cursor.close()


def _queue_stats_for_tags(conn, tags: List[str]) -> Dict[str, Dict]:
    if not tags:
        return {}

    cursor = _dict_cursor(conn)
    placeholders = ', '.join(['%s'] * len(tags))
    try:
        cursor.execute(
            f"""
            SELECT
                tag_name,
                SUM(CASE WHEN status = 'waiting' THEN 1 ELSE 0 END) AS waiting_count,
                SUM(CASE WHEN status = 'flashing' THEN 1 ELSE 0 END) AS flashing_count,
                MAX(CASE WHEN status = 'flashing' THEN id ELSE NULL END) AS active_request_id
            FROM flash_queue
            WHERE tag_name IN ({placeholders}) AND status IN ('waiting', 'flashing')
            GROUP BY tag_name
            """,
            tuple(tags),
        )

        stats = {}
        for row in cursor.fetchall():
            waiting = int(row.get('waiting_count') or 0)
            flashing = int(row.get('flashing_count') or 0)
            stats[row['tag_name']] = {
                'waiting_count': waiting,
                'flashing_count': flashing,
                'queue_depth': waiting + flashing,
                'active_request_id': row.get('active_request_id'),
            }
        return stats
    finally:
        cursor.close()


def _queue_position(conn, row: Dict) -> Optional[int]:
    if row.get('status') != 'waiting':
        return None

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM flash_queue
            WHERE tag_name = %s
              AND (
                status = 'flashing'
                OR (
                    status = 'waiting'
                    AND (created_at < %s OR (created_at = %s AND id < %s))
                )
              )
            """,
            (row['tag_name'], row['created_at'], row['created_at'], row['id']),
        )
        ahead_count = int(cursor.fetchone()[0])
        return ahead_count + 1
    finally:
        cursor.close()


def list_eligible_devices(username: str) -> List[Dict]:
    conn = create_db_connection()
    try:
        devices = [device for device in _get_user_accessible_devices(conn, username) if device['status'] == 'connected']
        stats_by_tag = _queue_stats_for_tags(conn, [device['tag_name'] for device in devices])

        result = []
        for device in devices:
            stats = stats_by_tag.get(device['tag_name'], {})
            flashing_count = stats.get('flashing_count', 0)
            result.append({
                **device,
                'usage_mode': _normalize_usage_mode(device.get('usage_mode')),
                'queue_depth': stats.get('queue_depth', 0),
                'waiting_count': stats.get('waiting_count', 0),
                'flashing_count': flashing_count,
                'active_request_id': stats.get('active_request_id'),
                'is_busy': bool(device.get('locked_by_user')) or flashing_count > 0,
            })
        return result
    finally:
        conn.close()


def enqueue_request(username: str, project_name: str, tag_name: str, board_type: str, firmware_path: str) -> Dict:
    if board_type not in SUPPORTED_BOARDS:
        raise ValueError('Unsupported board type')

    resolved_path = _safe_workspace_file(username, project_name, firmware_path)
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    user_lock_acquired = False

    try:
        user_lock_acquired = _acquire_user_lock(conn, username)
        if not user_lock_acquired:
            raise RuntimeError('Could not acquire enqueue lock for this user')

        cursor.execute(
            """
            SELECT id, status
            FROM flash_queue
            WHERE user_id = %s AND status IN ('waiting', 'flashing')
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (username,),
        )
        active_row = cursor.fetchone()
        if active_row:
            raise ValueError(f"User already has an active flash request ({active_row['status']})")

        device = _get_device_by_tag(conn, tag_name)
        if not device:
            raise ValueError('Device not found')
        usage_mode = _normalize_usage_mode(device.get('usage_mode'))
        if usage_mode == 'block':
            raise ValueError('This device is blocked and cannot receive flash requests')

        allowed_tags = {device_row['tag_name'] for device_row in _get_user_accessible_devices(conn, username)}
        if tag_name not in allowed_tags:
            if usage_mode == 'share':
                raise ValueError('This shared device is not assigned to your account')
            raise ValueError('Permission denied for this device')
        if device['status'] != 'connected':
            raise ValueError('Device is not connected')

        cursor.execute(
            """
            INSERT INTO flash_queue (user_id, tag_name, board_type, firmware_path, status)
            VALUES (%s, %s, %s, %s, 'waiting')
            """,
            (username, tag_name, board_type, resolved_path),
        )
        request_id = cursor.lastrowid
        conn.commit()

        cursor.execute('SELECT * FROM flash_queue WHERE id = %s', (request_id,))
        return _serialize_request(cursor.fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        if user_lock_acquired:
            _release_user_lock(conn, username)
        cursor.close()
        conn.close()


def get_active_request(username: str) -> Optional[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT *
            FROM flash_queue
            WHERE user_id = %s AND status IN ('waiting', 'flashing')
            ORDER BY CASE WHEN status = 'flashing' THEN 0 ELSE 1 END, created_at ASC, id ASC
            LIMIT 1
            """,
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        payload = _serialize_request(row)
        payload['queue_position'] = _queue_position(conn, row)
        return payload
    finally:
        cursor.close()
        conn.close()


def list_history(username: str, page: int = 1, limit: int = 20, status: Optional[str] = None) -> Dict:
    page = max(page, 1)
    limit = max(min(limit, 100), 1)
    offset = (page - 1) * limit

    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        params: List = [username]
        where_clause = 'WHERE user_id = %s'
        if status:
            where_clause += ' AND status = %s'
            params.append(status)

        cursor.execute(f'SELECT COUNT(*) AS total FROM flash_queue {where_clause}', tuple(params))
        total = int(cursor.fetchone()['total'])

        cursor.execute(
            f"""
            SELECT id, user_id, tag_name, board_type, firmware_path, status,
                   created_at, started_at, completed_at
            FROM flash_queue
            {where_clause}
            ORDER BY created_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )

        return {
            'items': [_serialize_request(row) for row in cursor.fetchall()],
            'page': page,
            'limit': limit,
            'total': total,
        }
    finally:
        cursor.close()
        conn.close()


def get_request_detail(username: str, request_id: int) -> Optional[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT *
            FROM flash_queue
            WHERE id = %s AND user_id = %s
            LIMIT 1
            """,
            (request_id, username),
        )
        row = cursor.fetchone()
        if not row:
            return None

        payload = _serialize_request(row)
        payload['queue_position'] = _queue_position(conn, row)
        return payload
    finally:
        cursor.close()
        conn.close()


def cancel_waiting_request(username: str, request_id: int) -> Optional[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    user_lock_acquired = False
    try:
        user_lock_acquired = _acquire_user_lock(conn, username)
        if not user_lock_acquired:
            raise RuntimeError('Could not acquire cancel lock for this user')

        cursor.execute(
            """
            UPDATE flash_queue
            SET status = 'cancelled', completed_at = NOW(),
                log_output = CONCAT_WS('\n', NULLIF(log_output, ''), 'Request cancelled by user.')
            WHERE id = %s AND user_id = %s AND status = 'waiting'
            """,
            (request_id, username),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            return None

        conn.commit()
        cursor.execute('SELECT * FROM flash_queue WHERE id = %s', (request_id,))
        return _serialize_request(cursor.fetchone())
    except Exception:
        conn.rollback()
        raise
    finally:
        if user_lock_acquired:
            _release_user_lock(conn, username)
        cursor.close()
        conn.close()


def list_worker_candidates() -> List[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT id, user_id, tag_name, board_type, firmware_path, status, created_at
            FROM flash_queue
            WHERE status = 'waiting'
            ORDER BY created_at ASC, id ASC
            """
        )

        seen_tags = set()
        candidates = []
        for row in cursor.fetchall():
            if row['tag_name'] in seen_tags:
                continue
            seen_tags.add(row['tag_name'])
            candidates.append(row)
        return candidates
    finally:
        cursor.close()
        conn.close()


def claim_request_for_processing(request_id: int) -> Optional[Tuple[Dict, Dict]]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT *
            FROM flash_queue
            WHERE id = %s AND status = 'waiting'
            LIMIT 1
            """,
            (request_id,),
        )
        request_row = cursor.fetchone()
        if not request_row:
            conn.rollback()
            return None

        cursor.execute(
            """
            SELECT *
            FROM devices
            WHERE tag_name = %s
            LIMIT 1
            """,
            (request_row['tag_name'],),
        )
        device = cursor.fetchone()
        if not device:
            conn.rollback()
            return None
        if device['status'] != 'connected' or device.get('locked_by_user'):
            conn.rollback()
            return None

        cursor.execute(
            """
            UPDATE devices
            SET locked_by_user = %s
            WHERE tag_name = %s AND status = 'connected' AND locked_by_user IS NULL
            """,
            (request_row['user_id'], request_row['tag_name']),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None

        cursor.execute(
            """
            UPDATE flash_queue
            SET status = 'flashing',
                started_at = NOW(),
                log_output = CONCAT_WS('\n', NULLIF(log_output, ''), 'Worker claimed request and started flashing.')
            WHERE id = %s AND status = 'waiting'
            """,
            (request_id,),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return None

        conn.commit()
        cursor.execute('SELECT * FROM flash_queue WHERE id = %s', (request_id,))
        claimed_row = cursor.fetchone()
        return _serialize_request(claimed_row), device
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_request_by_id(request_id: int) -> Optional[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute('SELECT * FROM flash_queue WHERE id = %s', (request_id,))
        row = cursor.fetchone()
        return _serialize_request(row)
    finally:
        cursor.close()
        conn.close()


def default_slot_id_for_device(device: Dict) -> Optional[int]:
    if not device.get('is_virtualized'):
        return None

    total_slots = int(device.get('total_slots') or 0)
    return 0 if total_slots <= 1 else None


def append_serial_log(request_id: int, chunk: str) -> bool:
    if not chunk:
        return False

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE flash_queue
            SET serial_log = CONCAT(COALESCE(serial_log, ''), %s)
            WHERE id = %s AND status = 'flashing'
            """,
            (chunk, request_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def append_log_output(request_id: int, message: str) -> bool:
    if not message:
        return False

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE flash_queue
            SET log_output = CONCAT_WS('\n', NULLIF(log_output, ''), %s)
            WHERE id = %s AND status = 'flashing'
            """,
            (message, request_id),
        )
        conn.commit()
        return cursor.rowcount == 1
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def finalize_request(request_id: int, username: str, tag_name: str, status: str, log_output: str) -> bool:
    if status not in ('success', 'failed'):
        raise ValueError('Invalid final status')

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE flash_queue
            SET status = %s,
                completed_at = NOW(),
                log_output = %s
            WHERE id = %s AND status = 'flashing'
            """,
            (status, log_output, request_id),
        )
        updated = cursor.rowcount == 1

        cursor.execute(
            """
            UPDATE devices
            SET locked_by_user = NULL
            WHERE tag_name = %s AND locked_by_user = %s
            """,
            (tag_name, username),
        )
        conn.commit()
        return updated
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def fail_flashing_requests_for_device(tag_name: str, reason: str) -> List[Dict]:
    conn = create_db_connection()
    cursor = _dict_cursor(conn)
    try:
        cursor.execute(
            """
            SELECT id, user_id, tag_name, board_type, firmware_path, status,
                   created_at, started_at, completed_at, log_output, serial_log
            FROM flash_queue
            WHERE tag_name = %s AND status = 'flashing'
            ORDER BY started_at ASC, id ASC
            """,
            (tag_name,),
        )
        rows = cursor.fetchall()
        if not rows:
            conn.rollback()
            return []

        cursor.execute(
            """
            UPDATE flash_queue
            SET status = 'failed',
                completed_at = NOW(),
                log_output = CONCAT_WS('\n', NULLIF(log_output, ''), %s)
            WHERE tag_name = %s AND status = 'flashing'
            """,
            (reason, tag_name),
        )
        cursor.execute(
            """
            UPDATE devices
            SET locked_by_user = NULL
            WHERE tag_name = %s
            """,
            (tag_name,),
        )
        conn.commit()
        return [_serialize_request(row) for row in rows]
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()
