"""
WebSocket event handlers for Flask-SocketIO.

Global device events continue to broadcast to the shared `updates` room.
User-specific flash/serial events are emitted to `user:{username}` rooms.
"""

import os
from typing import Dict, Optional

import jwt
from flask import request
from flask_socketio import emit, join_room

from app.services import flash_serial_session
from app.socketio_instance import socketio

SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')
_SOCKET_USERS: Dict[str, str] = {}


def _user_room(username: str) -> str:
    return f'user:{username}'


def _extract_username_from_socket(auth) -> Optional[str]:
    token = None

    if isinstance(auth, dict):
        token = auth.get('token')

    if not token:
        auth_header = request.headers.get('Authorization', '')
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            token = parts[1]

    if not token:
        token = request.args.get('token')

    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload.get('username')
    except jwt.InvalidTokenError:
        return None


@socketio.on('connect')
def on_connect(auth=None):
    join_room('updates')

    username = _extract_username_from_socket(auth)
    if username:
        _SOCKET_USERS[request.sid] = username
        join_room(_user_room(username))

    emit('connected', {
        'message': 'WebSocket connected to Remote Lab',
        'username': username,
    })


@socketio.on('disconnect')
def on_disconnect():
    flash_serial_session.unregister_viewer_sid(request.sid)
    _SOCKET_USERS.pop(request.sid, None)


@socketio.on('flash_serial_view_start')
def on_flash_serial_view_start(data):
    username = _SOCKET_USERS.get(request.sid)
    request_id = int((data or {}).get('request_id') or 0)
    if not username or request_id <= 0:
        return

    flash_serial_session.register_viewer(request_id, username, request.sid)


@socketio.on('flash_serial_view_stop')
def on_flash_serial_view_stop(data):
    request_id = int((data or {}).get('request_id') or 0)
    if request_id <= 0:
        return

    flash_serial_session.unregister_viewer(request_id, request.sid)


@socketio.on('flash_serial_pong')
def on_flash_serial_pong(data):
    request_id = int((data or {}).get('request_id') or 0)
    if request_id <= 0:
        return

    flash_serial_session.record_pong(request_id, request.sid)


def broadcast_device_connected(tag_name: str, port: str, device_type: str):
    socketio.emit('device_connected', {
        'tag_name': tag_name,
        'port': port,
        'type': device_type,
        'status': 'connected',
    }, room='updates')


def broadcast_device_disconnected(tag_name: str, port: str):
    socketio.emit('device_disconnected', {
        'tag_name': tag_name,
        'port': port,
        'status': 'disconnected',
    }, room='updates')


def broadcast_device_locked(tag_name: str, locked_by: str):
    socketio.emit('device_locked', {
        'tag_name': tag_name,
        'locked_by': locked_by,
    }, room='updates')


def broadcast_device_unlocked(tag_name: str):
    socketio.emit('device_unlocked', {
        'tag_name': tag_name,
    }, room='updates')


def broadcast_flash_started(tag_name: str, user: str):
    socketio.emit('flash_started', {
        'tag_name': tag_name,
        'user': user,
    }, room='updates')


def broadcast_flash_done(tag_name: str, user: str, success: bool, log: str = ''):
    socketio.emit('flash_done', {
        'tag_name': tag_name,
        'user': user,
        'success': success,
        'log': log,
    }, room='updates')


def broadcast_flash_task_update(request_id: int, tag_name: str, user: str, status: str, log: str = ''):
    socketio.emit('flash_task_update', {
        'request_id': request_id,
        'tag_name': tag_name,
        'user': user,
        'status': status,
        'log': log,
    }, room='updates')


def broadcast_flash_serial_started(request_id: int, tag_name: str, user: str, duration_seconds: int, baud_rate: int):
    socketio.emit('flash_serial_started', {
        'request_id': request_id,
        'tag_name': tag_name,
        'user': user,
        'duration_seconds': duration_seconds,
        'baud_rate': baud_rate,
    }, room=_user_room(user))


def broadcast_flash_serial_chunk(request_id: int, tag_name: str, user: str, chunk: str):
    socketio.emit('flash_serial_chunk', {
        'request_id': request_id,
        'tag_name': tag_name,
        'user': user,
        'chunk': chunk,
    }, room=_user_room(user))


def broadcast_flash_serial_finished(request_id: int, tag_name: str, user: str, reason: str):
    socketio.emit('flash_serial_finished', {
        'request_id': request_id,
        'tag_name': tag_name,
        'user': user,
        'reason': reason,
    }, room=_user_room(user))
