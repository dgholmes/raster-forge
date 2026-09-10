"""SocketIO handlers.

Live job progress is an enhancement, never the source of truth: the frontend
polls GET /api/jobs/<id> as its reliable baseline (correct across reloads and
reconnects) and treats these events as a way to update sooner.
"""
from flask import current_app
from flask_socketio import emit

_socketio = None


def register_ws_handlers(socketio):
    global _socketio
    _socketio = socketio

    @socketio.on("connect")
    def _on_connect():
        emit("connected", {"service": current_app.config.get("SERVICE_NAME", "rasterforge")})

    @socketio.on("ping")
    def _on_ping(data=None):
        emit("pong", data or {})


def emit_job_progress(payload: dict) -> None:
    """Broadcast a job update. Safe to call from a worker thread; silently
    does nothing if SocketIO is not initialised (e.g. under pytest)."""
    if _socketio is None:
        return
    try:
        _socketio.emit("job:progress", payload)
    except Exception:
        # Progress push is best-effort — never let it fail a job.
        pass
