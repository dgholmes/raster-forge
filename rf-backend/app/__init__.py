"""Application factory.

Wires config, SQLAlchemy, JWT, CORS and SocketIO, registers blueprints,
creates tables, seeds the admin, starts the job queue, and recovers any job
left mid-flight by a restart.
"""
from __future__ import annotations

import sys

from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO

from config import Config

from .models import db

# Threading mode: no eventlet/gevent, which keeps this dependency-light and
# well-behaved on the Windows machines this runs on.
socketio = SocketIO(async_mode="threading")
jwt = JWTManager()


def _force_utf8_console() -> None:
    """Korean Windows consoles default to cp949 and raise UnicodeEncodeError
    on an em-dash or a Korean dataset name in a log line."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass


def create_app(config_class=Config, start_queue: bool = True) -> Flask:
    _force_utf8_console()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # SQLite needs a busy timeout: the worker thread commits progress while
    # request threads read, and the default 5s is easy to exceed under load.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {})
        app.config["SQLALCHEMY_ENGINE_OPTIONS"].update({
            "connect_args": {"timeout": 30, "check_same_thread": False},
        })

    # --- extensions ---
    db.init_app(app)
    jwt.init_app(app)

    origins = app.config["CORS_ORIGINS"]
    origins_list = "*" if origins == "*" else [o.strip() for o in origins.split(",")]
    CORS(app, origins=origins_list, supports_credentials=(origins != "*"))
    socketio.init_app(app, cors_allowed_origins=origins)

    # --- blueprints ---
    from .admin import admin_bp
    from .auth import auth_bp, seed_admin_user
    from .datasets import datasets_bp
    from .downloads import downloads_bp
    from .health import health_bp
    from .jobs import init_queue, jobs_bp, recover_interrupted_jobs
    from .publish import publish_bp
    from .ws import register_ws_handlers

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(publish_bp)
    app.register_blueprint(downloads_bp)
    app.register_blueprint(admin_bp)

    register_ws_handlers(socketio)

    # --- error handlers ---
    @app.errorhandler(413)
    def _too_large(_):
        return jsonify({
            "error_code": "invalid_request",
            "error": (
                f"That file exceeds the {app.config['MAX_UPLOAD_MB']} MB upload limit."
            ),
        }), 413

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"error_code": "not_found", "error": "Not found."}), 404

    # --- first run ---
    with app.app_context():
        db.create_all()
        seed_admin_user()
        app.config["STORAGE_ROOT"].mkdir(parents=True, exist_ok=True)

    init_queue(app)
    if start_queue:
        recover_interrupted_jobs(app)

    return app
