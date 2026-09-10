"""Publishing.

The PRD's preferred architecture, taken literally: the worker generates the
pyramid into persistent storage that the tile server already reads, so
publishing copies nothing. It validates the output, writes metadata.json and
records the URL — an O(1) metadata operation rather than an 8 GB file move.

That is also what makes publish independently retryable: if publishing fails,
the expensive raster work is already on disk and only the cheap step reruns.

`Publisher` is a one-method interface so a future RsyncPublisher (for a
deployment where processing and hosting are genuinely on different hosts)
slots in without the pipeline knowing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from .validate import ValidationResult, validate_bounds, validate_tile_output

__all__ = ["Publisher", "LocalPublisher", "PublishError", "PublishResult"]


class PublishError(RuntimeError):
    """Publishing failed. The tiles are intact; only this step needs retrying."""


class PublishResult:
    def __init__(self, url_template: str, metadata_path: Path, validation: ValidationResult):
        self.url_template = url_template
        self.metadata_path = metadata_path
        self.validation = validation


class Publisher(Protocol):
    def publish(
        self,
        *,
        slug: str,
        tiles_dir: Path,
        metadata_path: Path,
        min_zoom: int,
        max_zoom: int,
        bounds: list[float] | None,
        center: list[float] | None,
        display_name: str,
        extra: dict | None = None,
    ) -> PublishResult: ...


class LocalPublisher:
    """Publishes by validating and registering — no file transfer.

    Tiles are served straight out of the directory they were generated into,
    resolved by slug. `tile_public_base` is what the UI's Copy URL yields.
    """

    def __init__(self, tile_public_base: str) -> None:
        self.tile_public_base = (tile_public_base or "").rstrip("/")

    def url_template_for(self, slug: str) -> str:
        return f"{self.tile_public_base}/{slug}/{{z}}/{{x}}/{{y}}.png"

    def publish(
        self,
        *,
        slug: str,
        tiles_dir: Path,
        metadata_path: Path,
        min_zoom: int,
        max_zoom: int,
        bounds: list[float] | None,
        center: list[float] | None,
        display_name: str,
        extra: dict | None = None,
    ) -> PublishResult:
        validation = validate_tile_output(tiles_dir, min_zoom, max_zoom)
        if not validation.ok:
            raise PublishError("; ".join(validation.errors))

        bound_errors = validate_bounds(tuple(bounds) if bounds else None)
        # Missing bounds degrade the preview's auto-fit but do not make the
        # tiles unusable, so this is a warning rather than a hard failure.
        warnings = bound_errors

        url_template = self.url_template_for(slug)
        document = {
            "name": display_name,
            "slug": slug,
            "scheme": "xyz",
            "profile": "mercator",
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "bounds": bounds,
            "center": center,
            "tile_url_template": url_template,
            "tile_count": validation.tile_count,
            "size_bytes": validation.size_bytes,
            "zoom_levels": validation.zoom_levels,
            "published_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "warnings": warnings,
        }
        if extra:
            document.update(extra)

        try:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            raise PublishError(f"Could not write metadata.json: {exc}") from exc

        return PublishResult(url_template, metadata_path, validation)
