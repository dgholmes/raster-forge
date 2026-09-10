"""Database models.

The load-bearing rule from PRD §6:

    Dataset  !=  ProcessingJob  !=  TileOutput  !=  Published asset

One uploaded raster may produce many outputs over its life (XYZ 14-21, then
XYZ 14-22, later a COG, later PMTiles). Nothing here assumes
`1 GeoTIFF = 1 tile folder`, which is what keeps the post-MVP roadmap from
needing a schema rewrite.

Bounds are stored as four explicit floats *and* a JSON blob so a PostGIS
geometry column can be added later without reshaping anything.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

ROLES = ("admin", "user")

# Dataset lifecycle (PRD §6.2)
DATASET_STATUSES = (
    "uploaded", "inspecting", "ready", "queued", "processing",
    "publishing", "completed", "publish_failed", "failed", "cancelled",
)
JOB_STATUSES = ("queued", "processing", "publishing", "completed", "failed", "cancelled")
ACTIVE_JOB_STATUSES = ("queued", "processing", "publishing")

# Dataset states that mean "work is in flight". A dataset must never be left
# in one of these once its job has reached a terminal state — that is what
# makes a dataset look permanently busy and refuse every new job.
ACTIVE_DATASET_STATUSES = ("inspecting", "queued", "processing", "publishing")


def _uuid4() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    datasets = db.relationship("Dataset", back_populates="owner", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": _iso(self.created_at),
        }


class Dataset(db.Model):
    __tablename__ = "datasets"

    id = db.Column(db.String(36), primary_key=True, default=_uuid4)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

    display_name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)

    source_filename = db.Column(db.String(255), nullable=False)
    source_path = db.Column(db.Text, nullable=False)
    source_size = db.Column(db.BigInteger, default=0)

    status = db.Column(db.String(32), nullable=False, default="uploaded", index=True)
    error_code = db.Column(db.String(40), nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    owner = db.relationship("User", back_populates="datasets")
    raster_metadata = db.relationship(
        "RasterMetadata", back_populates="dataset", uselist=False,
        cascade="all, delete-orphan",
    )
    jobs = db.relationship(
        "ProcessingJob", back_populates="dataset", cascade="all, delete-orphan",
        order_by="ProcessingJob.created_at.desc()",
    )
    outputs = db.relationship(
        "TileOutput", back_populates="dataset", cascade="all, delete-orphan",
        order_by="TileOutput.created_at.desc()",
    )

    @property
    def latest_job(self) -> "ProcessingJob | None":
        return self.jobs[0] if self.jobs else None

    @property
    def published_output(self) -> "TileOutput | None":
        for output in self.outputs:
            if output.is_published:
                return output
        return None

    def to_dict(self, deep: bool = False) -> dict:
        data = {
            "id": self.id,
            "display_name": self.display_name,
            "slug": self.slug,
            "source_filename": self.source_filename,
            "source_size": self.source_size,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "owner": self.owner.username if self.owner else None,
            "owner_id": self.owner_id,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "metadata": self.raster_metadata.to_dict() if self.raster_metadata else None,
        }
        latest = self.latest_job
        data["latest_job"] = latest.to_dict() if latest else None
        published = self.published_output
        data["published_output"] = published.to_dict() if published else None
        if deep:
            data["jobs"] = [j.to_dict() for j in self.jobs]
            data["outputs"] = [o.to_dict() for o in self.outputs]
        return data


class RasterMetadata(db.Model):
    __tablename__ = "raster_metadata"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(
        db.String(36), db.ForeignKey("datasets.id"), nullable=False, unique=True, index=True
    )

    driver = db.Column(db.String(40))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    band_count = db.Column(db.Integer)

    crs_name = db.Column(db.String(255))
    epsg = db.Column(db.Integer)
    is_geographic = db.Column(db.Boolean, default=False)

    pixel_size_x = db.Column(db.Float)
    pixel_size_y = db.Column(db.Float)
    gsd_m = db.Column(db.Float)

    # Explicit columns now; a PostGIS geometry can join these later.
    min_lon = db.Column(db.Float)
    min_lat = db.Column(db.Float)
    max_lon = db.Column(db.Float)
    max_lat = db.Column(db.Float)
    center_lon = db.Column(db.Float)
    center_lat = db.Column(db.Float)

    has_alpha = db.Column(db.Boolean, default=False)
    nodata_values = db.Column(db.JSON)
    bands = db.Column(db.JSON)
    recommended_max_zoom = db.Column(db.Integer)
    nodata_warning = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(db.JSON)

    created_at = db.Column(db.DateTime, default=_utcnow)

    dataset = db.relationship("Dataset", back_populates="raster_metadata")

    @property
    def bounds(self) -> list[float] | None:
        vals = (self.min_lon, self.min_lat, self.max_lon, self.max_lat)
        return list(vals) if all(v is not None for v in vals) else None

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "width": self.width,
            "height": self.height,
            "band_count": self.band_count,
            "crs_name": self.crs_name,
            "epsg": self.epsg,
            "is_geographic": self.is_geographic,
            "pixel_size_x": self.pixel_size_x,
            "pixel_size_y": self.pixel_size_y,
            "gsd_m": self.gsd_m,
            "bounds": self.bounds,
            "center": (
                [self.center_lon, self.center_lat]
                if self.center_lon is not None and self.center_lat is not None
                else None
            ),
            "has_alpha": self.has_alpha,
            "nodata_values": self.nodata_values,
            "bands": self.bands,
            "recommended_max_zoom": self.recommended_max_zoom,
            "nodata_warning": self.nodata_warning,
        }


class ProcessingJob(db.Model):
    __tablename__ = "processing_jobs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid4)
    dataset_id = db.Column(
        db.String(36), db.ForeignKey("datasets.id"), nullable=False, index=True
    )

    type = db.Column(db.String(40), nullable=False, default="xyz_tiles")
    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    current_step = db.Column(db.String(120), nullable=True)

    params = db.Column(db.JSON)

    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    error_code = db.Column(db.String(40), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    log_path = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    dataset = db.relationship("Dataset", back_populates="jobs")

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_JOB_STATUSES

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at:
            return None
        end = self.finished_at or _utcnow()
        start = self.started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return max(0.0, (end - start).total_seconds())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset.display_name if self.dataset else None,
            "type": self.type,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "params": self.params,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "duration_seconds": self.duration_seconds,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": _iso(self.created_at),
        }


class TileOutput(db.Model):
    __tablename__ = "tile_outputs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid4)
    dataset_id = db.Column(
        db.String(36), db.ForeignKey("datasets.id"), nullable=False, index=True
    )
    job_id = db.Column(db.String(36), db.ForeignKey("processing_jobs.id"), nullable=True)

    min_zoom = db.Column(db.Integer, nullable=False)
    max_zoom = db.Column(db.Integer, nullable=False)
    scheme = db.Column(db.String(20), nullable=False, default="xyz")
    profile = db.Column(db.String(20), nullable=False, default="mercator")
    resampling = db.Column(db.String(20), nullable=False, default="bilinear")

    tile_count = db.Column(db.Integer, default=0)
    size_bytes = db.Column(db.BigInteger, default=0)
    output_path = db.Column(db.Text, nullable=False)
    public_url_template = db.Column(db.Text, nullable=True)
    bounds = db.Column(db.JSON)

    normalised = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=False, index=True)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)

    dataset = db.relationship("Dataset", back_populates="outputs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "job_id": self.job_id,
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "scheme": self.scheme,
            "profile": self.profile,
            "resampling": self.resampling,
            "tile_count": self.tile_count,
            "size_bytes": self.size_bytes,
            "public_url_template": self.public_url_template,
            "bounds": self.bounds,
            "normalised": self.normalised,
            "is_published": self.is_published,
            "published_at": _iso(self.published_at),
            "created_at": _iso(self.created_at),
        }
