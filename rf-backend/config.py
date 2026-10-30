"""Application configuration.

Everything is environment-driven with working development defaults, so the
backend runs out of the box on SQLite with a seeded admin, while production
overrides via .env or real environment variables.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

# Load .env next to this file so systemd/gunicorn without an EnvironmentFile
# still pick up secrets.
load_dotenv(BACKEND_DIR / ".env")


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    # --- Secrets (override in production) ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=_int("JWT_ACCESS_TOKEN_EXPIRES_HOURS", 8))

    # --- Database ---
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'rasterforge.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- CORS ---
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    # --- Storage ---
    # Root of the dataset tree: storage/datasets/{uuid}/{source,working,output,...}
    STORAGE_ROOT = Path(
        os.environ.get("STORAGE_ROOT", str(PROJECT_ROOT / "storage"))
    ).resolve()

    # --- Tile publishing ---
    # Base URL the generated XYZ endpoint is advertised at. In development the
    # backend serves tiles itself; in production point this at Nginx.
    TILE_PUBLIC_BASE = os.environ.get(
        "TILE_PUBLIC_BASE", "http://localhost:9010/tiles"
    ).rstrip("/")
    # Optional: a directory a static tile host serves (e.g. Apache's /2Dtile).
    # When set, publishing mirrors each pyramid to <TILE_PUBLISH_DIR>/<slug>/
    # so TILE_PUBLIC_BASE can point at that host. Empty = serve from storage.
    TILE_PUBLISH_DIR = os.environ.get("TILE_PUBLISH_DIR", "").strip()

    # --- GDAL ---
    # Optional overrides; discovery finds QGIS/OSGeo4W automatically.
    GDAL_ROOT = os.environ.get("GDAL_ROOT", "")
    GDAL2TILES_PATH = os.environ.get("GDAL2TILES_PATH", "")
    GDAL2TILES_PROCESSES = _int("GDAL2TILES_PROCESSES", 2)

    # --- Resource protection (PRD §18) ---
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 8192)
    MAX_RASTER_PIXELS = _int("MAX_RASTER_PIXELS", 6_000_000_000)
    MAX_CONCURRENT_RASTER_JOBS = _int("MAX_CONCURRENT_RASTER_JOBS", 2)
    MIN_FREE_DISK_GB = _int("MIN_FREE_DISK_GB", 10)
    JOB_TIMEOUT_MINUTES = _int("JOB_TIMEOUT_MINUTES", 240)

    # --- Queue ---
    QUEUE_BACKEND = os.environ.get("QUEUE_BACKEND", "thread")  # thread | rq
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # --- Demo / bootstrap ---
    # DEMO_MODE accepts ANY credentials. Off by default: the PRD requires real
    # authentication before upload.
    DEMO_MODE = _bool("DEMO_MODE", "0")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@rasterforge.local")

    # --- Server ---
    PORT = _int("PORT", 9010)
    DEBUG = _bool("FLASK_DEBUG", "1")
    SERVICE_NAME = os.environ.get("SERVICE_NAME", "rasterforge")

    # Flask's own upload cap. Werkzeug rejects anything larger outright.
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
