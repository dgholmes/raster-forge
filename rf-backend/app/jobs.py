"""Processing jobs — /api/jobs and the worker entrypoint.

The worker runs in a pool thread and therefore opens its **own** Flask app
context. `current_app` is a thread-local proxy bound to the request thread;
reading it from a pool worker raises "Working outside of application
context". Every config value the worker needs is read inside its own context.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from .auth import current_user
from .errors import api_error, classify_gdal_error
from .models import (
    ACTIVE_JOB_STATUSES,
    Dataset,
    ProcessingJob,
    TileOutput,
    db,
)
from .storage import (
    free_disk_bytes,
    logs_dir,
    metadata_dir,
    source_dir,
    storage_root,
    tiles_dir,
    working_dir,
)
from .ws import emit_job_progress

from raster.analysis import (
    DEFAULT_RESAMPLING,
    MAX_SUPPORTED_ZOOM,
    RESAMPLING_METHODS,
    estimate_tile_count,
)
from raster.gdal_runner import GdalNotFound, GdalProcessCancelled, GdalRunner
from raster.inspect import RasterInspectionError, inspect_raster
from raster.joblog import JobLog
from raster.pipeline import PipelineError, TileParams, run_tile_pipeline
from raster.publisher import LocalPublisher, PublishError
from raster.queue import ThreadJobQueue
from raster.validate import validate_tile_output

jobs_bp = Blueprint("jobs", __name__)

# Average bytes per generated PNG tile, measured across test pyramids. Only
# used for the pre-flight disk estimate, which is deliberately conservative.
AVG_TILE_BYTES = 40 * 1024


# --------------------------------------------------------------------------
# Queue wiring
# --------------------------------------------------------------------------

def init_queue(app) -> ThreadJobQueue:
    """Build the job queue and attach it to the app."""
    backend = app.config.get("QUEUE_BACKEND", "thread")
    if backend != "thread":
        app.logger.warning(
            "QUEUE_BACKEND=%s is not available in this build; using the "
            "in-process thread queue.", backend
        )

    queue = ThreadJobQueue(
        runner_fn=lambda job_id: run_job(app, job_id),
        max_workers=app.config["MAX_CONCURRENT_RASTER_JOBS"],
    )
    app.extensions["raster_queue"] = queue
    return queue


def get_queue(app=None) -> ThreadJobQueue:
    target = app or current_app
    return target.extensions["raster_queue"]


def recover_interrupted_jobs(app) -> int:
    """Fail any job left mid-flight by a server restart.

    In-process jobs cannot survive a restart, so rather than leave a job
    stuck at 'processing' forever, mark it failed with an honest message and
    let the user re-run it. The generated tiles, if any, stay on disk.
    """
    with app.app_context():
        stale = ProcessingJob.query.filter(
            ProcessingJob.status.in_(ACTIVE_JOB_STATUSES)
        ).all()
        for job in stale:
            job.status = "failed"
            job.error_code = "gdal_failure"
            job.error_message = (
                "Interrupted by a server restart. The job did not finish; run it again."
            )
            job.finished_at = datetime.now(timezone.utc)
            if job.dataset and job.dataset.status in ACTIVE_JOB_STATUSES:
                job.dataset.status = "ready"
        if stale:
            db.session.commit()
            print(f"[jobs] recovered {len(stale)} interrupted job(s)", flush=True)
        return len(stale)


# --------------------------------------------------------------------------
# Job creation
# --------------------------------------------------------------------------

def _can_access(dataset: Dataset) -> bool:
    user = current_user()
    if current_app.config["DEMO_MODE"] and user is None:
        return True
    if user is None:
        return False
    return user.is_admin or dataset.owner_id == user.id


def _parse_tile_params(data: dict, dataset: Dataset) -> tuple[TileParams | None, tuple | None]:
    """Validate the request body into TileParams.

    This is where user input stops being user input: every value that reaches
    a GDAL argument is range-checked or drawn from a fixed enum here.
    """
    meta = dataset.raster_metadata
    default_max = (meta.recommended_max_zoom if meta and meta.recommended_max_zoom else 18)

    raw_min = data.get("min_zoom", 14)
    raw_max = data.get("max_zoom", default_max)
    try:
        min_zoom = int(raw_min)
        max_zoom = int(raw_max)
    except (TypeError, ValueError):
        return None, api_error("invalid_request", 400, "Zoom levels must be whole numbers.")

    if not (0 <= min_zoom <= MAX_SUPPORTED_ZOOM and 0 <= max_zoom <= MAX_SUPPORTED_ZOOM):
        return None, api_error(
            "invalid_request", 400,
            f"Zoom levels must be between 0 and {MAX_SUPPORTED_ZOOM}.",
        )
    if min_zoom > max_zoom:
        return None, api_error(
            "invalid_request", 400,
            "Minimum zoom cannot be greater than maximum zoom.",
        )

    resampling = (data.get("resampling") or DEFAULT_RESAMPLING).strip().lower()
    if resampling not in RESAMPLING_METHODS:
        return None, api_error(
            "invalid_request", 400,
            f"Resampling must be one of: {', '.join(RESAMPLING_METHODS)}.",
        )

    nodata_mode = (data.get("nodata_mode") or "auto").strip().lower()
    if nodata_mode not in ("auto", "preserve", "remove"):
        return None, api_error(
            "invalid_request", 400,
            "NoData handling must be auto, preserve or remove.",
        )

    return TileParams(
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        resampling=resampling,
        nodata_mode=nodata_mode,
        processes=current_app.config["GDAL2TILES_PROCESSES"],
    ), None


def _disk_precheck(dataset: Dataset, params: TileParams) -> tuple | None:
    """Refuse a job that clearly cannot fit (PRD §18)."""
    meta = dataset.raster_metadata
    if not meta:
        return None

    from raster.inspect import parse_gdalinfo
    try:
        info = parse_gdalinfo(meta.metadata_json or {})
        estimated_tiles = estimate_tile_count(info, params.min_zoom, params.max_zoom)
    except Exception:
        estimated_tiles = 0

    estimated_bytes = estimated_tiles * AVG_TILE_BYTES
    # Normalisation writes a full working copy, so budget for that too.
    estimated_bytes += (dataset.source_size or 0)

    reserve = current_app.config["MIN_FREE_DISK_GB"] * 1024 ** 3
    free = free_disk_bytes(storage_root())

    if free < estimated_bytes + reserve:
        return api_error(
            "insufficient_disk", 507,
            f"This job needs roughly {estimated_bytes / 1024 ** 3:.1f} GB plus a "
            f"{current_app.config['MIN_FREE_DISK_GB']} GB reserve, but only "
            f"{free / 1024 ** 3:.1f} GB is free.",
        )
    return None


@jobs_bp.route("/api/datasets/<dataset_id>/tile-jobs", methods=["POST"])
@jwt_required()
def create_tile_job(dataset_id: str):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        body, status = api_error("not_found", 404, "Dataset not found.")
        return jsonify(body), status
    if not _can_access(dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    existing = ProcessingJob.query.filter(
        ProcessingJob.dataset_id == dataset.id,
        ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
    ).first()
    if existing:
        body, status = api_error(
            "job_conflict", 409,
            "A job is already running for this dataset.",
        )
        return jsonify(body), status

    data = request.get_json(silent=True) or {}
    params, error = _parse_tile_params(data, dataset)
    if error:
        body, status = error
        return jsonify(body), status

    error = _disk_precheck(dataset, params)
    if error:
        body, status = error
        return jsonify(body), status

    job = ProcessingJob(
        dataset_id=dataset.id,
        type="xyz_tiles",
        status="queued",
        progress=0,
        current_step="Queued",
        params=params.to_dict(),
    )
    db.session.add(job)
    db.session.flush()
    job.log_path = str(logs_dir(dataset.id) / f"job-{job.id}.log")

    dataset.status = "queued"
    dataset.error_code = None
    dataset.error_message = None
    db.session.commit()

    get_queue().submit(job.id)
    return jsonify(job.to_dict()), 201


# --------------------------------------------------------------------------
# Job routes
# --------------------------------------------------------------------------

@jobs_bp.route("/api/jobs", methods=["GET"])
@jwt_required()
def list_jobs():
    user = current_user()
    query = ProcessingJob.query.join(Dataset, ProcessingJob.dataset_id == Dataset.id)
    if user is not None and not user.is_admin:
        query = query.filter(Dataset.owner_id == user.id)
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    rows = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()
    return jsonify([j.to_dict() for j in rows]), 200


@jobs_bp.route("/api/jobs/<job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id: str):
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        body, status = api_error("not_found", 404, "Job not found.")
        return jsonify(body), status
    if job.dataset and not _can_access(job.dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status
    return jsonify(job.to_dict()), 200


@jobs_bp.route("/api/jobs/<job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job(job_id: str):
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        body, status = api_error("not_found", 404, "Job not found.")
        return jsonify(body), status
    if job.dataset and not _can_access(job.dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status
    if not job.is_active:
        body, status = api_error(
            "invalid_request", 409,
            f"This job is already {job.status} and cannot be cancelled.",
        )
        return jsonify(body), status

    outcome = get_queue().cancel(job.id)

    # Only write the terminal state when the worker definitely will not.
    # Deciding from job.status instead would race: this request can hold a
    # stale `queued` read while the worker is committing `processing`, and
    # writing `cancelled` over it strands the dataset at `processing`.
    if outcome in ("dropped", "unknown"):
        db.session.refresh(job)
        if job.is_active:
            job.status = "cancelled"
            job.current_step = "Cancelled"
            job.error_code = "cancelled"
            job.error_message = "The job was cancelled."
            job.finished_at = datetime.now(timezone.utc)
            if job.dataset:
                job.dataset.status = "ready"
            db.session.commit()

    db.session.refresh(job)
    return jsonify(job.to_dict()), 200


@jobs_bp.route("/api/jobs/<job_id>/logs", methods=["GET"])
@jwt_required()
def get_job_logs(job_id: str):
    job = db.session.get(ProcessingJob, job_id)
    if not job:
        body, status = api_error("not_found", 404, "Job not found.")
        return jsonify(body), status
    if job.dataset and not _can_access(job.dataset):
        body, status = api_error("permission_denied", 403)
        return jsonify(body), status

    tail = min(5000, max(1, int(request.args.get("tail", 500))))
    if not job.log_path:
        return jsonify({"lines": [], "path": None}), 200
    lines = JobLog(Path(job.log_path)).tail(tail)
    return jsonify({"lines": lines, "path": job.log_path}), 200


# --------------------------------------------------------------------------
# Worker
# --------------------------------------------------------------------------

def run_job(app, job_id: str) -> None:
    """Worker entrypoint. Runs in a pool thread with its own app context."""
    with app.app_context():
        job = db.session.get(ProcessingJob, job_id)
        if job is None:
            return
        dataset = job.dataset
        if dataset is None:
            job.status = "failed"
            job.error_code = "not_found"
            job.error_message = "The dataset for this job no longer exists."
            job.finished_at = datetime.now(timezone.utc)
            db.session.commit()
            return

        queue = get_queue(app)
        runner = GdalRunner()
        queue.register_runner(job_id, runner)

        log = JobLog(Path(job.log_path or (logs_dir(dataset.id) / f"job-{job.id}.log")))
        last_write = [0.0]

        def set_progress(pct: int, step: str) -> None:
            """Persist progress, throttled to at most one write per second.

            Without the throttle a fast-moving ruler would issue hundreds of
            commits per minute and, on SQLite, contend with the API thread.
            """
            now = time.monotonic()
            if now - last_write[0] < 1.0 and pct < 100:
                return
            last_write[0] = now
            job.progress = max(0, min(100, int(pct)))
            job.current_step = step[:120]
            db.session.commit()
            emit_job_progress({
                "job_id": job.id,
                "dataset_id": dataset.id,
                "status": job.status,
                "progress": job.progress,
                "current_step": job.current_step,
            })

        def finish(status: str, code: str | None = None, message: str | None = None) -> None:
            job.status = status
            job.error_code = code
            job.error_message = message
            job.finished_at = datetime.now(timezone.utc)
            db.session.commit()
            emit_job_progress({
                "job_id": job.id,
                "dataset_id": dataset.id,
                "status": status,
                "progress": job.progress,
                "current_step": job.current_step,
                "error_code": code,
                "error_message": message,
            })

        # -- start --------------------------------------------------------
        # Cancelled while queued: return without ever advertising the dataset
        # as processing, so a cancel that lands during startup cannot leave
        # the dataset looking busy.
        if queue.is_cancelled(job_id):
            log.warn("cancel", "Cancelled before processing started.")
            dataset.status = "ready"
            finish("cancelled", "cancelled", "The job was cancelled.")
            return

        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.current_step = "Starting"
        dataset.status = "processing"
        db.session.commit()

        log.info("upload", f"Dataset {dataset.display_name} ({dataset.source_size:,} bytes)")

        params_dict = job.params or {}
        params = TileParams(
            min_zoom=int(params_dict.get("min_zoom", 14)),
            max_zoom=int(params_dict.get("max_zoom", 18)),
            resampling=params_dict.get("resampling", DEFAULT_RESAMPLING),
            nodata_mode=params_dict.get("nodata_mode", "auto"),
            processes=int(params_dict.get("processes", 2)),
        )
        timeout_s = app.config["JOB_TIMEOUT_MINUTES"] * 60
        publisher = LocalPublisher.from_config(app.config)

        source = source_dir(dataset.id, create=False) / "original.tif"
        if not source.is_file():
            log.error("validate", f"Source file missing: {source}")
            dataset.status = "failed"
            finish("failed", "corrupted_raster", "The source file is missing from storage.")
            return

        try:
            info = inspect_raster(source)
            log.info(
                "inspect",
                f"EPSG:{info.epsg} {info.width}x{info.height} {info.band_count} bands",
            )

            result = run_tile_pipeline(
                source=source,
                working_dir=working_dir(dataset.id),
                tiles_dir=tiles_dir(dataset.id),
                params=params,
                info=info,
                log=log,
                progress=set_progress,
                runner=runner,
                should_cancel=lambda: queue.is_cancelled(job_id),
                timeout=timeout_s,
            )

        except GdalProcessCancelled:
            log.warn("cancel", "Job cancelled by user request.")
            dataset.status = "ready"
            job.progress = job.progress or 0
            finish("cancelled", "cancelled", "The job was cancelled.")
            return
        except GdalNotFound as exc:
            log.error("gdal", str(exc))
            dataset.status = "failed"
            finish("failed", "gdal_missing", str(exc))
            return
        except TimeoutError as exc:
            log.error("timeout", str(exc))
            dataset.status = "failed"
            finish("failed", "gdal_failure", str(exc))
            return
        except (PipelineError, RasterInspectionError) as exc:
            technical = "\n".join(log.tail(80))
            code, message = classify_gdal_error(f"{exc}\n{technical}")
            # A pipeline error already carries a human sentence; prefer it.
            message = str(exc) or message
            log.error("pipeline", str(exc))
            dataset.status = "failed"
            dataset.error_code = code
            dataset.error_message = message
            finish("failed", code, message)
            return
        except Exception as exc:  # pragma: no cover - defensive
            log.error("pipeline", f"Unexpected error: {exc!r}")
            dataset.status = "failed"
            finish("failed", "gdal_failure", f"Unexpected processing error: {exc}")
            return

        # -- validate -----------------------------------------------------
        set_progress(96, "Validating output")
        validation = validate_tile_output(result.tiles_dir, result.min_zoom, result.max_zoom)
        if not validation.ok:
            for err in validation.errors:
                log.error("validate", err)
            dataset.status = "failed"
            finish("failed", "validation_failed", "; ".join(validation.errors))
            return
        log.info(
            "validate",
            f"All zoom levels {result.min_zoom}-{result.max_zoom} present, "
            f"{validation.tile_count:,} tiles",
        )

        # -- record the output --------------------------------------------
        meta = dataset.raster_metadata
        bounds = meta.bounds if meta else None
        center = (
            [meta.center_lon, meta.center_lat]
            if meta and meta.center_lon is not None else None
        )

        output = TileOutput(
            dataset_id=dataset.id,
            job_id=job.id,
            min_zoom=result.min_zoom,
            max_zoom=result.max_zoom,
            scheme="xyz",
            profile="mercator",
            resampling=params.resampling,
            tile_count=validation.tile_count,
            size_bytes=validation.size_bytes,
            output_path=str(result.tiles_dir),
            bounds=bounds,
            normalised=result.normalised,
        )
        db.session.add(output)
        db.session.commit()

        # -- publish ------------------------------------------------------
        job.status = "publishing"
        dataset.status = "publishing"
        set_progress(98, "Publishing")

        try:
            published = publisher.publish(
                slug=dataset.slug,
                tiles_dir=result.tiles_dir,
                metadata_path=metadata_dir(dataset.id) / "metadata.json",
                min_zoom=result.min_zoom,
                max_zoom=result.max_zoom,
                bounds=bounds,
                center=center,
                display_name=dataset.display_name,
                extra={"dataset_id": dataset.id, "resampling": params.resampling},
            )
        except PublishError as exc:
            log.error("publish", str(exc))
            # Tiles are fine; only publishing failed. Do NOT fail the whole job
            # into a state that would make the user re-run the expensive part.
            dataset.status = "publish_failed"
            dataset.error_code = "publish_failed"
            dataset.error_message = str(exc)
            job.progress = 98
            finish("failed", "publish_failed", str(exc))
            return

        for other in dataset.outputs:
            if other.id != output.id:
                other.is_published = False
        output.is_published = True
        output.published_at = datetime.now(timezone.utc)
        output.public_url_template = published.url_template

        dataset.status = "completed"
        dataset.error_code = None
        dataset.error_message = None
        job.progress = 100
        job.current_step = "Complete"
        log.info("publish", published.url_template)
        finish("completed")
