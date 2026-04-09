# file: backend/app/socketio_instance.py
"""
Singleton SocketIO instance — import từ module này ở mọi nơi
để tránh circular import.
"""
from flask_socketio import SocketIO

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="eventlet",
    logger=False,
    engineio_logger=False,
)
