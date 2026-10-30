"""Datasets — /api/datasets.

Upload is the security boundary of the whole product, so validation is
layered and ordered cheapest-first:

    1. extension allowlist  (.tif / .tiff)
    2. TIFF magic bytes     (the filename is not evidence)
    3. gdalinfo opens it    (the only real proof it is a raster)

The upload is streamed to disk in chunks — these files are gigabytes and
`file.read()` would put one in memory. On any failure the dataset directory
is removed so a rejected upload leaves nothing behind.
"""
from __future__ import annotations

import re
import unicodedata

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from .auth import current_user
from .errors import api_error, classify_gdal_error
from .models import ACTIVE_JOB_STATUSES, Dataset, ProcessingJob, RasterMetadata, db
from .storage import (
    PathTraversal,
    delete_dataset_tree,
    free_disk_bytes,
    source_dir,
    storage_root,
)

from raster.analysis import decide_nodata, recommend_max_zoom
from raster.gdal_runner import GdalNotFound
from raster.publisher import LocalPublisher, PublishError
from raster.inspect import RasterInfo, RasterInspectionError, inspect_raster

datasets_bp = Blueprint("datasets", __name__, url_prefix="/api/datasets")

ALLOWED_EXTENSIONS = (".tif", ".tiff")
# Classic TIFF little/big endian, and BigTIFF little/big endian.
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
UPLOAD_CHUNK = 8 * 1024 * 1024


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

def slugify(display_name: str, dataset_id: str) -> str:
    """URL-safe slug from a display name, falling back to the id.

    Korean names (the common case here) ASCII-fold to nothing, so rather than
    emit an empty or mangled slug we use a short id. The slug is user-editable
    afterwards, and nothing on the filesystem depends on it.
    """
    text = unicodedata.normalize("NFKD", display_name or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)[:60].strip("-")
    return text or f"ds-{dataset_id[:8]}"


def unique_slug(base: str, exclude_id: str | None = None) -> str:
    """Append -2, -3, ... until the slug is free."""
    candidate = base
    suffix = 2
    while True:
        query = Dataset.query.filter_by(slug=candidate)
        if exclude_id:
            query = query.filter(Dataset.id != exclude_id)
        if not query.first():
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def is_valid_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value or "")) and len(value) <= 80


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _can_access(dataset: Dataset) -> bool:
    user = current_user()
    if current_app.config["DEMO_MODE"] and user is None:
        return True
    if user is None:
        return False
    return user.is_admin or dataset.owner_id == user.id


def _store_metadata(dataset: Dataset, info: RasterInfo) -> RasterMetadata:
    """Persist parsed metadata, replacing any previous inspection."""
    meta = dataset.raster_metadata or RasterMetadata(dataset_id=dataset.id)
    bounds = info.bounds_wgs84
    center = info.center_wgs84
    decision = decide_nodata(info, "auto")

    meta.driver = info.driver
    meta.width = info.width
    meta.height = info.height
    meta.band_count = info.band_count
    meta.crs_name = info.crs_name
    meta.epsg = info.epsg
    meta.is_geographic = info.is_geographic
    meta.pixel_size_x = info.pixel_size_x
    meta.pixel_size_y = info.pixel_size_y
    meta.gsd_m = info.gsd_m
    meta.min_lon, meta.min_lat, meta.max_lon, meta.max_lat = bounds if bounds else (None,) * 4
    meta.center_lon, meta.center_lat = center if center else (None, None)
    meta.has_alpha = info.has_alpha
    meta.nodata_values = info.nodata_values
    meta.bands = [b.to_dict() for b in info.bands]
    meta.recommended_max_zoom = recommend_max_zoom(info)
    meta.nodata_warning = decision.warning
    meta.metadata_json = info.to_dict()

    if meta.id is None:
        db.session.add(meta)
    return meta


def _inspect_and_store(dataset: Dataset, path) -> tuple[RasterMetadata | None, tuple | None]:
    """Inspect a raster and persist the result. Returns (metadata, error)."""
    try:
        info = inspect_raster(path)
    except GdalNotFound as exc:
        return None, api_error("gdal_missing", 503, str(exc))
    except RasterInspectionError as exc:
        code, message = classify_gdal_error(str(exc))
        if code == "gdal_failure":
            code, message = "corrupted_raster", str(exc)
        return None, api_error(code, 400, message)

    max_pixels = current_app.config["MAX_RASTER_PIXELS"]
    if max_pixels and info.pixel_count > max_pixels:
        return None, api_error(
            "raster_too_large", 413,
            f"This raster has {info.pixel_count:,} pixels, above the server limit "
            f"of {max_pixels:,}.",
        )

    return _store_metadata(dataset, info), None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@datasets_bp.route("", methods=["GET"])
@jwt_required()
def list_datasets():
    """Datasets the caller may see: their own, or everything for an admin."""
    user = current_user()
    query = Dataset.query
    if user is not None and not user.is_admin:
        query = query.filter(Dataset.owner_id == user.id)
    rows = query.order_by(Dataset.created_at.desc()).all()
    return jsonify([d.to_dict() for d in rows]), 200


@datasets_bp.route("", methods=["POST"])
@jwt_required()
def upload_dataset():
    if "file" not in request.files:
        body, status = api_error("invalid_request", 400, "No file was uploaded.")
        return jsonify(body), status

    upload = request.files["file"]
    filename = (upload.filename or "").strip()
    if not filename:
        body, status = api_error("invalid_request", 400, "The uploaded file has no name.")
        return jsonify(body), status

    # 1. extension allowlist
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        body, status = api_error("unsupported_file", 400)
        return jsonify(body), status

    # 2. magic bytes — the filename is a claim, not evidence
    head = upload.stream.read(4)
    upload.stream.seek(0)
    if not any(head.startswith(magic) for magic in TIFF_MAGIC):
        body, status = api_error(
            "unsupported_file", 400,
            "That file is not a TIFF. Its contents do not start with a TIFF header, "
            "whatever the extension says.",
        )
        return jsonify(body), status

    user = current_user()
    display_name = (request.form.get("display_name") or "").strip() or filename.rsplit(".", 1)[0]

    dataset = Dataset(
        display_name=display_name[:255],
        slug="pending",
        source_filename=filename[:255],
        source_path="",
        source_size=0,
        status="inspecting",
        owner_id=user.id if user else None,
    )
    db.session.add(dataset)
    db.session.flush()  # assigns dataset.id

    requested_slug = (request.form.get("slug") or "").strip().lower()
    base_slug = requested_slug if is_valid_slug(requested_slug) else slugify(display_name, dataset.id)
    dataset.slug = unique_slug(base_slug, exclude_id=dataset.id)

    # 3. stream to disk — never read a multi-GB upload into memory
    target = source_dir(dataset.id) / "original.tif"
    written = 0
    try:
        with target.open("wb") as fh:
            while True:
                chunk = upload.stream.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                fh.write(chunk)
                written += len(chunk)
    except OSError as exc:
        db.session.rollback()
        delete_dataset_tree(dataset.id)
        body, status = api_error("insufficient_disk", 507, f"Could not save the upload: {exc}")
        return jsonify(body), status

    if written == 0:
        db.session.rollback()
        delete_dataset_tree(dataset.id)
        body, status = api_error("invalid_request", 400, "The uploaded file was empty.")
        return jsonify(body), status

    dataset.source_path = str(target)
    dataset.source_size = written

    # 4. gdalinfo is the only real proof this is a usable raster
    _, error = _inspect_and_store(dataset, target)
    if error is not None:
        db.session.rollback()
        delete_dataset_tree(dataset.id)
        body, status = error
        return jsonify(body), status

    dataset.status = "ready"
    db.session.commit()
    return jsonify(dataset.to_dict()), 201


@datasets_bp.route("/<dataset_id>", methods=["GET"])
@jwt_required()
def get_dataset(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status
    return jsonify(dataset.to_dict(deep=True)), 200


@datasets_bp.route("/<dataset_id>", methods=["PATCH"])
@jwt_required()
def update_dataset(dataset_id: str):
    """Rename, or change the slug. Renaming never moves anything on disk."""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    data = request.get_json(silent=True) or {}

    if "display_name" in data:
        name = (data.get("display_name") or "").strip()
        if not name:
            body, status = api_error("invalid_request", 400, "Display name cannot be empty.")
            return jsonify(body), status
        dataset.display_name = name[:255]

    if "slug" in data:
        slug = (data.get("slug") or "").strip().lower()
        if not is_valid_slug(slug):
            body, status = api_error(
                "invalid_request", 400,
                "A slug may contain only lowercase letters, numbers and single hyphens.",
            )
            return jsonify(body), status
        new_slug = unique_slug(slug, exclude_id=dataset.id)
        if new_slug != dataset.slug:
            publisher = LocalPublisher.from_config(current_app.config)
            # The static-host mirror (if any) is keyed by slug: move it first,
            # so a failure leaves both the DB and the tile host unchanged.
            try:
                publisher.rename(dataset.slug, new_slug)
            except PublishError as exc:
                body, status = api_error("publish_failed", 500, str(exc))
                return jsonify(body), status
            dataset.slug = new_slug
            # The advertised URL embeds the slug, so republish the template.
            for output in dataset.outputs:
                if output.public_url_template:
                    output.public_url_template = publisher.url_template_for(new_slug)

    db.session.commit()
    return jsonify(dataset.to_dict()), 200


@datasets_bp.route("/<dataset_id>", methods=["DELETE"])
@jwt_required()
def delete_dataset(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    active = ProcessingJob.query.filter(
        ProcessingJob.dataset_id == dataset.id,
        ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
    ).first()
    if active:
        body, status = api_error(
            "job_conflict", 409,
            "This dataset has a running job. Cancel it before deleting.",
        )
        return jsonify(body), status

    user = current_user()
    print(f"[audit] dataset delete id={dataset.id} slug={dataset.slug} "
          f"by={user.username if user else 'demo'}", flush=True)

    slug = dataset.slug
    db.session.delete(dataset)
    db.session.commit()
    try:
        delete_dataset_tree(dataset_id)
    except PathTraversal:
        pass
    LocalPublisher.from_config(current_app.config).unpublish(slug)
    return jsonify({"ok": True}), 200


@datasets_bp.route("/<dataset_id>/metadata", methods=["GET"])
@jwt_required()
def get_metadata(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status
    if not dataset.raster_metadata:
        body, status = api_error("not_found", 404, "This dataset has not been inspected yet.")
        return jsonify(body), status
    return jsonify(dataset.raster_metadata.to_dict()), 200


@datasets_bp.route("/<dataset_id>/inspect", methods=["POST"])
@jwt_required()
def reinspect(dataset_id: str):
    """Re-run gdalinfo — useful after a GDAL install is fixed."""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    source = source_dir(dataset.id, create=False) / "original.tif"
    if not source.is_file():
        body, status = api_error("not_found", 404, "The source file is missing from storage.")
        return jsonify(body), status

    _, error = _inspect_and_store(dataset, source)
    if error is not None:
        db.session.rollback()
        body, status = error
        return jsonify(body), status

    if dataset.status in ("failed", "uploaded", "inspecting"):
        dataset.status = "ready"
        dataset.error_code = None
        dataset.error_message = None
    db.session.commit()
    return jsonify(dataset.to_dict()), 200


@datasets_bp.route("/storage-stats", methods=["GET"])
@jwt_required()
def storage_stats():
    root = storage_root()
    return jsonify({
        "storage_root": str(root),
        "free_bytes": free_disk_bytes(root),
    }), 200
