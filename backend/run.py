# file: backend/run.py
"""
Entry point — chạy với socketio.run() thay vì app.run()
để eventlet WebSocket hoạt động đúng.
"""
import eventlet
eventlet.monkey_patch()

from app import create_app
from app.socketio_instance import socketio

app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)