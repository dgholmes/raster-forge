"""Publishing retry, preview metadata, and the public tile route.

The tile route is the only place in the product where user-controlled path
segments ({z}/{x}/{y}) reach the filesystem. It is confined to a single
dataset's `output/tiles` directory via `safe_join`, so a traversal attempt
cannot reach `source/original.tif` — which is what keeps source rasters
private while their tiles are public.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from .auth import current_user
from .errors import api_error
from .models import Dataset, db
from .storage import PathTraversal, metadata_dir, safe_join, tiles_dir

from raster.publisher import LocalPublisher, PublishError

publish_bp = Blueprint("publish", __name__)

TILE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _can_access(dataset: Dataset) -> bool:
    user = current_user()
    if current_app.config["DEMO_MODE"] and user is None:
        return True
    if user is None:
        return False
    return user.is_admin or dataset.owner_id == user.id


@publish_bp.route("/api/datasets/<dataset_id>/publish", methods=["POST"])
@jwt_required()
def republish(dataset_id: str):
    """Retry publishing without re-running the raster processing."""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    output = dataset.published_output or (dataset.outputs[0] if dataset.outputs else None)
    if output is None:
        body, status = api_error(
            "invalid_request", 409,
            "This dataset has no generated tiles to publish. Run tile generation first.",
        )
        return jsonify(body), status

    meta = dataset.raster_metadata
    publisher = LocalPublisher.from_config(current_app.config)
    try:
        result = publisher.publish(
            slug=dataset.slug,
            tiles_dir=tiles_dir(dataset.id, create=False),
            metadata_path=metadata_dir(dataset.id) / "metadata.json",
            min_zoom=output.min_zoom,
            max_zoom=output.max_zoom,
            bounds=meta.bounds if meta else None,
            center=(
                [meta.center_lon, meta.center_lat]
                if meta and meta.center_lon is not None else None
            ),
            display_name=dataset.display_name,
            extra={"dataset_id": dataset.id, "resampling": output.resampling},
        )
    except PublishError as exc:
        dataset.status = "publish_failed"
        dataset.error_code = "publish_failed"
        dataset.error_message = str(exc)
        db.session.commit()
        body, status = api_error("publish_failed", 500, str(exc))
        return jsonify(body), status

    for other in dataset.outputs:
        other.is_published = other.id == output.id
    output.is_published = True
    output.published_at = datetime.now(timezone.utc)
    output.public_url_template = result.url_template
    output.tile_count = result.validation.tile_count
    output.size_bytes = result.validation.size_bytes

    dataset.status = "completed"
    dataset.error_code = None
    dataset.error_message = None
    db.session.commit()

    user = current_user()
    print(f"[audit] publish dataset={dataset.id} slug={dataset.slug} "
          f"by={user.username if user else 'demo'}", flush=True)

    return jsonify(dataset.to_dict(deep=True)), 200


@publish_bp.route("/api/datasets/<dataset_id>/preview", methods=["GET"])
@jwt_required()
def preview(dataset_id: str):
    """Everything the map preview needs in one call."""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    output = dataset.published_output
    meta = dataset.raster_metadata
    return jsonify({
        "dataset_id": dataset.id,
        "slug": dataset.slug,
        "display_name": dataset.display_name,
        "status": dataset.status,
        "is_published": bool(output),
        "tile_url_template": output.public_url_template if output else None,
        "min_zoom": output.min_zoom if output else None,
        "max_zoom": output.max_zoom if output else None,
        "tile_count": output.tile_count if output else 0,
        "size_bytes": output.size_bytes if output else 0,
        "published_at": output.to_dict()["published_at"] if output else None,
        "bounds": meta.bounds if meta else None,
        "center": (
            [meta.center_lon, meta.center_lat]
            if meta and meta.center_lon is not None else None
        ),
    }), 200


@publish_bp.route("/api/datasets/<dataset_id>/outputs", methods=["GET"])
@jwt_required()
def list_outputs(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status
    return jsonify([o.to_dict() for o in dataset.outputs]), 200


# --------------------------------------------------------------------------
# Public tile serving
# --------------------------------------------------------------------------

@publish_bp.route("/tiles/<slug>/<int:z>/<int:x>/<path:rest>", methods=["GET"])
def serve_tile(slug: str, z: int, x: int, rest: str):
    """Serve one tile. Public by design — this is the endpoint other apps consume.

    Resolution is by *slug*, never by dataset id, and the path is confined to
    the dataset's tiles directory. Both matter: the id is not advertised, and
    `safe_join` guarantees `rest` cannot climb out of `output/tiles`.
    """
    dataset = Dataset.query.filter_by(slug=slug).first()
    if dataset is None:
        return "", 404

    output = dataset.published_output
    if output is None:
        # Generated but unpublished tiles are not public.
        return "", 404

    if not any(rest.lower().endswith(ext) for ext in TILE_EXTENSIONS):
        return "", 404
    if not (0 <= z <= 22) or x < 0:
        return "", 404

    try:
        root = tiles_dir(dataset.id, create=False)
        path = safe_join(root, str(z), str(x), rest)
    except PathTraversal:
        return "", 404

    if not path.is_file():
        return "", 404

    response = send_file(path, conditional=True)
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@publish_bp.route("/api/internal/resolve-slug", methods=["GET"])
def resolve_slug():
    """Map a published slug to its dataset id, for Nginx's `auth_request`.

    This exists so Nginx can serve tiles straight off the shared storage
    volume (Option A in infra/nginx/rasterforge.conf) instead of proxying
    every tile through Flask. It returns no body — only the X-Dataset-Id
    header, which Nginx captures via auth_request_set.

    Deliberately unauthenticated so Nginx need not hold a token, and
    deliberately minimal: it reveals only that a *published* slug maps to an
    opaque id. Keep it on an internal interface or firewall it; the shipped
    config marks the location `internal`.
    """
    slug = (request.args.get("slug") or "").strip().lower()
    if not slug:
        return "", 404

    dataset = Dataset.query.filter_by(slug=slug).first()
    if dataset is None or dataset.published_output is None:
        return "", 404

    response = current_app.response_class(status=200)
    response.headers["X-Dataset-Id"] = dataset.id
    return response


@publish_bp.route("/tiles/<slug>/metadata.json", methods=["GET"])
def serve_tile_metadata(slug: str):
    """The published metadata document, alongside the tiles."""
    dataset = Dataset.query.filter_by(slug=slug).first()
    if dataset is None or dataset.published_output is None:
        return "", 404
    path = metadata_dir(dataset.id, create=False) / "metadata.json"
    if not path.is_file():
        return "", 404
    response = send_file(path, mimetype="application/json", conditional=True)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
