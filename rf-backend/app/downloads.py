"""Downloads — /api/datasets/<id>/download/*.

The tiles archive uses ZIP_STORED, not DEFLATE: PNG tiles are already
compressed, so deflating them burns CPU for roughly nothing. ZIP64 is enabled
because a real orthomosaic pyramid exceeds the 4 GB classic-ZIP ceiling.

The archive is built once and cached next to the tiles, then rebuilt only if
the pyramid changed. A free-disk check runs first so a download request can
never fill the volume.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, send_file
from flask_jwt_extended import jwt_required

from .auth import current_user
from .errors import api_error
from .models import Dataset, db
from .storage import (
    dir_size_bytes,
    free_disk_bytes,
    metadata_dir,
    output_dir,
    source_dir,
    tiles_dir,
    working_dir,
)

downloads_bp = Blueprint("downloads", __name__, url_prefix="/api/datasets")


def _can_access(dataset: Dataset) -> bool:
    user = current_user()
    if current_app.config["DEMO_MODE"] and user is None:
        return True
    if user is None:
        return False
    return user.is_admin or dataset.owner_id == user.id


def _load(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return None, api_error("not_found", 404, "Dataset not found.")
    if not _can_access(dataset):
        return None, api_error("permission_denied", 403)
    return dataset, None


@downloads_bp.route("/<dataset_id>/download/source", methods=["GET"])
@jwt_required()
def download_source(dataset_id: str):
    dataset, error = _load(dataset_id)
    if error:
        body, status = error
        return jsonify(body), status

    path = source_dir(dataset.id, create=False) / "original.tif"
    if not path.is_file():
        body, status = api_error("not_found", 404, "The source file is missing from storage.")
        return jsonify(body), status
    # Name the download from the slug, never from the raw uploaded filename.
    return send_file(path, as_attachment=True, download_name=f"{dataset.slug}.tif")


@downloads_bp.route("/<dataset_id>/download/working", methods=["GET"])
@jwt_required()
def download_working(dataset_id: str):
    dataset, error = _load(dataset_id)
    if error:
        body, status = error
        return jsonify(body), status

    path = working_dir(dataset.id, create=False) / "clean.tif"
    if not path.is_file():
        body, status = api_error(
            "not_found", 404,
            "No normalised copy exists — this dataset was tiled from its source.",
        )
        return jsonify(body), status
    return send_file(path, as_attachment=True, download_name=f"{dataset.slug}_clean.tif")


@downloads_bp.route("/<dataset_id>/download/metadata", methods=["GET"])
@jwt_required()
def download_metadata(dataset_id: str):
    dataset, error = _load(dataset_id)
    if error:
        body, status = error
        return jsonify(body), status

    path = metadata_dir(dataset.id, create=False) / "metadata.json"
    if not path.is_file():
        body, status = api_error(
            "not_found", 404, "No metadata document — this dataset has not been published."
        )
        return jsonify(body), status
    return send_file(
        path, as_attachment=True,
        download_name=f"{dataset.slug}_metadata.json", mimetype="application/json",
    )


def _newest_mtime(root: Path) -> float:
    newest = 0.0
    for p in root.rglob("*.png"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
    return newest


def _build_tiles_zip(tiles_root: Path, zip_path: Path) -> None:
    """Write the pyramid to `zip_path`, stored (uncompressed)."""
    tmp = zip_path.with_suffix(".zip.part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for path in sorted(tiles_root.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(tiles_root)).replace("\\", "/"))
        tmp.replace(zip_path)
    finally:
        tmp.unlink(missing_ok=True)


@downloads_bp.route("/<dataset_id>/download/tiles", methods=["GET"])
@jwt_required()
def download_tiles(dataset_id: str):
    dataset, error = _load(dataset_id)
    if error:
        body, status = error
        return jsonify(body), status

    tiles_root = tiles_dir(dataset.id, create=False)
    if not tiles_root.is_dir() or not any(tiles_root.rglob("*.png")):
        body, status = api_error(
            "not_found", 404, "This dataset has no generated tiles to download."
        )
        return jsonify(body), status

    zip_path = output_dir(dataset.id) / f"{dataset.slug}_tiles.zip"

    # Rebuild only when missing or stale.
    needs_build = True
    if zip_path.is_file():
        try:
            needs_build = zip_path.stat().st_mtime < _newest_mtime(tiles_root)
        except OSError:
            needs_build = True

    if needs_build:
        required = dir_size_bytes(tiles_root)
        free = free_disk_bytes(output_dir(dataset.id))
        if free < required * 1.1:
            body, status = api_error(
                "packaging_failed", 507,
                f"Building the archive needs about {required / 1024 ** 3:.1f} GB but "
                f"only {free / 1024 ** 3:.1f} GB is free.",
            )
            return jsonify(body), status
        try:
            _build_tiles_zip(tiles_root, zip_path)
        except OSError as exc:
            body, status = api_error("packaging_failed", 500, f"Could not build the archive: {exc}")
            return jsonify(body), status

    return send_file(
        zip_path, as_attachment=True,
        download_name=f"{dataset.slug}_tiles.zip", mimetype="application/zip",
    )
