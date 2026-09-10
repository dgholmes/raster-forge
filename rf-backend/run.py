"""Server entrypoint.

    python run.py

Listens on port 9010 — the frontend's default API base URL.
(9005 is already used by another service on the lab machine.)
"""
from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    print(f"RasterForge API on http://localhost:{app.config['PORT']}", flush=True)
    print(f"  storage: {app.config['STORAGE_ROOT']}", flush=True)
    print(f"  tiles:   {app.config['TILE_PUBLIC_BASE']}/<slug>/{{z}}/{{x}}/{{y}}.png", flush=True)
    socketio.run(
        app,
        host="0.0.0.0",
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        allow_unsafe_werkzeug=True,  # dev server under SocketIO
    )
