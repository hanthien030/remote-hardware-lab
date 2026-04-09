# file: backend/app/__init__.py

import eventlet
eventlet.monkey_patch()  # Must be first — patches stdlib for async SocketIO

from flask import Flask, request, jsonify
from flask_cors import CORS
from config import Config
from .db import close_db_connection
from .socketio_instance import socketio


def create_app():
    """Application factory function."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Init SocketIO with app
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="eventlet",
    )

    # Enable CORS for REST API routes
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:3000", "http://localhost:5173", "http://localhost", "*"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True,
            "max_age": 3600
        }
    })

    # Handle OPTIONS requests for CORS preflight (before auth checks)
    @app.before_request
    def handle_preflight():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200

    # Register REST API blueprints
    from .routes.main import main_bp
    app.register_blueprint(main_bp)
    from .routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    from .routes.internal import internal_bp
    app.register_blueprint(internal_bp)
    from .routes.admin_hardware import admin_hw_bp
    app.register_blueprint(admin_hw_bp)
    from .routes.hardware import hw_bp
    app.register_blueprint(hw_bp)
    from .routes.flash_queue import flash_queue_bp
    app.register_blueprint(flash_queue_bp)
    from .routes.workspace import workspace_bp
    app.register_blueprint(workspace_bp)

    # Register WebSocket handlers (side-effect: decorators register on socketio)
    from . import ws_handlers  # noqa: F401

    # Start exactly one backend-owned queue worker in this process.
    from .services.flash_queue_worker import start_queue_worker_if_needed
    start_queue_worker_if_needed()

    app.teardown_appcontext(close_db_connection)
    return app
