"""Admin — /api/admin.

Includes the resolved GDAL environment, because "tiling fails on this
machine" is nearly always a GDAL discovery problem and an operator needs to
see what the server actually resolved without reading logs.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from .auth import admin_required, current_user
from .errors import api_error
from .models import Dataset, ProcessingJob, TileOutput, User, db
from .storage import dataset_root, dir_size_bytes, free_disk_bytes, storage_root

from raster.gdal_runner import gdal_diagnostics

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/stats", methods=["GET"])
@jwt_required()
@admin_required
def stats():
    root = storage_root()
    datasets = Dataset.query.all()

    per_dataset = []
    total_bytes = 0
    for d in datasets:
        try:
            size = dir_size_bytes(dataset_root(d.id, create=False))
        except Exception:
            size = 0
        total_bytes += size
        per_dataset.append({
            "id": d.id,
            "display_name": d.display_name,
            "slug": d.slug,
            "status": d.status,
            "size_bytes": size,
            "owner": d.owner.username if d.owner else None,
        })
    per_dataset.sort(key=lambda r: r["size_bytes"], reverse=True)

    failed = (
        ProcessingJob.query.filter(ProcessingJob.status == "failed")
        .order_by(ProcessingJob.created_at.desc())
        .limit(20).all()
    )

    from .jobs import get_queue
    queue = get_queue()

    return jsonify({
        "datasets": {
            "total": len(datasets),
            "published": sum(1 for d in datasets if d.status == "completed"),
            "failed": sum(1 for d in datasets if d.status == "failed"),
        },
        "jobs": {
            "total": ProcessingJob.query.count(),
            "active": queue.active_count(),
            "pending": queue.pending_count(),
            "max_concurrent": queue.max_workers,
            "failed": ProcessingJob.query.filter_by(status="failed").count(),
        },
        "outputs": {
            "total": TileOutput.query.count(),
            "published": TileOutput.query.filter_by(is_published=True).count(),
        },
        "storage": {
            "root": str(root),
            "used_bytes": total_bytes,
            "free_bytes": free_disk_bytes(root),
            "by_dataset": per_dataset[:50],
        },
        "gdal": gdal_diagnostics(),
        "limits": {
            "max_upload_mb": current_app.config["MAX_UPLOAD_MB"],
            "max_raster_pixels": current_app.config["MAX_RASTER_PIXELS"],
            "min_free_disk_gb": current_app.config["MIN_FREE_DISK_GB"],
            "job_timeout_minutes": current_app.config["JOB_TIMEOUT_MINUTES"],
        },
        "failed_jobs": [j.to_dict() for j in failed],
    }), 200


@admin_bp.route("/users", methods=["GET"])
@jwt_required()
@admin_required
def list_users():
    return jsonify([u.to_dict() for u in User.query.order_by(User.id.asc()).all()]), 200


@admin_bp.route("/users", methods=["POST"])
@jwt_required()
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()

    if not username or not password:
        body, status = api_error("invalid_request", 400, "Username and password are required.")
        return jsonify(body), status
    if role not in ("admin", "user"):
        body, status = api_error("invalid_request", 400, "Role must be admin or user.")
        return jsonify(body), status
    if User.query.filter_by(username=username).first():
        body, status = api_error("invalid_request", 409, "That username is already taken.")
        return jsonify(body), status

    user = User(username=username, email=(data.get("email") or None), role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    actor = current_user()
    print(f"[audit] user create username={username} role={role} "
          f"by={actor.username if actor else 'demo'}", flush=True)
    return jsonify(user.to_dict()), 201


@admin_bp.route("/users/<int:user_id>", methods=["PATCH"])
@jwt_required()
@admin_required
def update_user(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        body, status = api_error("not_found", 404, "User not found.")
        return jsonify(body), status

    data = request.get_json(silent=True) or {}
    actor = current_user()

    if "is_active" in data:
        active = bool(data["is_active"])
        if not active and actor is not None and actor.id == user.id:
            body, status = api_error(
                "invalid_request", 400, "You cannot deactivate your own account."
            )
            return jsonify(body), status
        user.is_active = active

    if "role" in data:
        role = (data.get("role") or "").strip()
        if role not in ("admin", "user"):
            body, status = api_error("invalid_request", 400, "Role must be admin or user.")
            return jsonify(body), status
        if role != "admin" and actor is not None and actor.id == user.id:
            body, status = api_error(
                "invalid_request", 400, "You cannot remove your own admin role."
            )
            return jsonify(body), status
        user.role = role

    if data.get("password"):
        user.set_password(data["password"])

    db.session.commit()
    print(f"[audit] user update id={user_id} by={actor.username if actor else 'demo'}", flush=True)
    return jsonify(user.to_dict()), 200
