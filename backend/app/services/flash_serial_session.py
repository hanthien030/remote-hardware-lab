import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from app.socketio_instance import socketio

PING_INTERVAL_SECONDS = int(os.getenv('FLASH_SERIAL_PING_INTERVAL_SECONDS', '120'))
PONG_TIMEOUT_SECONDS = int(os.getenv('FLASH_SERIAL_PONG_TIMEOUT_SECONDS', '10'))
CAPTURE_CHUNK_SECONDS = int(os.getenv('FLASH_SERIAL_CAPTURE_CHUNK_SECONDS', '5'))


@dataclass
class SerialSession:
    request_id: int
    username: str
    tag_name: str
    base_end_at: float
    viewer_sids: Set[str] = field(default_factory=set)
    last_ping_at: Optional[float] = None
    pong_deadline: Optional[float] = None
    stop_requested: bool = False


_sessions: Dict[int, SerialSession] = {}
_lock = threading.Lock()


def start_session(request_id: int, username: str, tag_name: str, base_hold_seconds: int) -> None:
    with _lock:
        _sessions[request_id] = SerialSession(
            request_id=request_id,
            username=username,
            tag_name=tag_name,
            base_end_at=time.time() + base_hold_seconds,
        )


def end_session(request_id: int) -> None:
    with _lock:
        _sessions.pop(request_id, None)


def register_viewer(request_id: int, username: str, sid: str) -> bool:
    with _lock:
        session = _sessions.get(request_id)
        if not session or session.username != username:
            return False

        session.viewer_sids.add(sid)
        session.pong_deadline = None
        return True


def unregister_viewer(request_id: int, sid: str) -> None:
    with _lock:
        session = _sessions.get(request_id)
        if not session:
            return
        session.viewer_sids.discard(sid)


def unregister_viewer_sid(sid: str) -> None:
    with _lock:
        for session in _sessions.values():
            session.viewer_sids.discard(sid)


def record_pong(request_id: int, sid: str) -> bool:
    with _lock:
        session = _sessions.get(request_id)
        if not session or sid not in session.viewer_sids:
            return False

        session.pong_deadline = None
        return True


def request_stop(request_id: int, username: str) -> bool:
    with _lock:
        session = _sessions.get(request_id)
        if not session or session.username != username:
            return False

        session.stop_requested = True
        session.viewer_sids.clear()
        session.pong_deadline = None
        return True


def is_session_owned_by(request_id: int, username: str) -> bool:
    with _lock:
        session = _sessions.get(request_id)
        return bool(session and session.username == username)


def should_continue(request_id: int) -> Tuple[bool, str]:
    with _lock:
        session = _sessions.get(request_id)
        if not session:
            return False, 'session_missing'

        if session.stop_requested:
            return False, 'user_stopped'

        now = time.time()
        if now < session.base_end_at:
            return True, 'base_hold'

        if session.pong_deadline and now > session.pong_deadline:
            session.viewer_sids.clear()
            session.pong_deadline = None
            return False, 'viewer_timeout'

        if not session.viewer_sids:
            return False, 'viewer_inactive'

        return True, 'extended'


def maybe_send_ping(request_id: int) -> bool:
    with _lock:
        session = _sessions.get(request_id)
        if not session:
            return False

        now = time.time()
        if now < session.base_end_at:
            return False
        if not session.viewer_sids:
            return False
        if session.pong_deadline is not None:
            return False
        if session.last_ping_at is not None and (now - session.last_ping_at) < PING_INTERVAL_SECONDS:
            return False

        session.last_ping_at = now
        session.pong_deadline = now + PONG_TIMEOUT_SECONDS
        target_sids = list(session.viewer_sids)
        payload = {
            'request_id': session.request_id,
            'tag_name': session.tag_name,
            'deadline_seconds': PONG_TIMEOUT_SECONDS,
        }

    for sid in target_sids:
        socketio.emit('flash_serial_ping', payload, room=sid)
    return True


def current_chunk_seconds(request_id: int) -> int:
    with _lock:
        session = _sessions.get(request_id)
        if not session:
            return CAPTURE_CHUNK_SECONDS

        now = time.time()
        if now < session.base_end_at:
            remaining = max(1, int(session.base_end_at - now))
            return max(1, min(CAPTURE_CHUNK_SECONDS, remaining))

        return CAPTURE_CHUNK_SECONDS
