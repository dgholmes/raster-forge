"""Health check — /api/health. No auth, used by the frontend status indicator."""
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "service": current_app.config.get("SERVICE_NAME", "rasterforge"),
    }), 200
