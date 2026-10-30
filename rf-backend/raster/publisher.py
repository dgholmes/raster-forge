"""Publishing.

The PRD's preferred architecture, taken literally: the worker generates the
pyramid into persistent storage that the tile server already reads, so
publishing copies nothing. It validates the output, writes metadata.json and
records the URL — an O(1) metadata operation rather than an 8 GB file move.

That is also what makes publish independently retryable: if publishing fails,
the expensive raster work is already on disk and only the cheap step reruns.

Optional second shape — `publish_dir` (config `TILE_PUBLISH_DIR`): a static
tile host (an Apache/Nginx directory listing such as the lab's `/2Dtile/`)
serves `<publish_dir>/<slug>/{z}/{x}/{y}.png`. When set, publishing also
mirrors the pyramid into `<publish_dir>/<slug>/` atomically: copy into a
sibling temp directory, then swap, so a half-copied folder is never visible
to the tile host. The storage tree stays the source of truth; the mirror is
rebuilt on every publish, renamed with the slug and removed with the dataset.

`Publisher` is a one-method interface so a future RsyncPublisher (for a
deployment where processing and hosting are genuinely on different hosts)
slots in without the pipeline knowing.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

from .validate import ValidationResult, validate_bounds, validate_tile_output

__all__ = ["Publisher", "LocalPublisher", "PublishError", "PublishResult"]

# Mirrors the API's slug rule. A slug is the only user-influenced value that
# becomes a directory name under publish_dir, so it is re-checked here rather
# than trusted: the API validates it too, but this module must be safe alone.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


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
    """Publishes by validating and registering, plus an optional directory mirror.

    Tiles are served straight out of the directory they were generated into,
    resolved by slug. `tile_public_base` is what the UI's Copy URL yields.
    With `publish_dir` set, the pyramid is also mirrored to
    `<publish_dir>/<slug>/` for a static tile host.
    """

    def __init__(self, tile_public_base: str, publish_dir: Path | str | None = None) -> None:
        self.tile_public_base = (tile_public_base or "").rstrip("/")
        text = str(publish_dir).strip() if publish_dir else ""
        self.publish_dir: Path | None = Path(text) if text else None

    @classmethod
    def from_config(cls, config: Mapping) -> "LocalPublisher":
        """Build from a Flask config mapping (TILE_PUBLIC_BASE, TILE_PUBLISH_DIR)."""
        return cls(config["TILE_PUBLIC_BASE"], config.get("TILE_PUBLISH_DIR"))

    def url_template_for(self, slug: str) -> str:
        return f"{self.tile_public_base}/{slug}/{{z}}/{{x}}/{{y}}.png"

    # -- directory mirror ---------------------------------------------------

    def published_dir_for(self, slug: str) -> Path | None:
        """`<publish_dir>/<slug>`, or None when mirroring is disabled.

        Raises PublishError for a slug that is not a plain directory name, so
        a bad value can never resolve outside publish_dir.
        """
        if self.publish_dir is None:
            return None
        if not _SLUG_RE.match(slug or ""):
            raise PublishError(f"Refusing to publish under an invalid slug: {slug!r}")
        return self.publish_dir / slug

    def _mirror(self, slug: str, tiles_dir: Path, metadata_document: dict) -> None:
        target = self.published_dir_for(slug)
        if target is None:
            return
        parent = target.parent
        token = uuid.uuid4().hex[:8]
        staging = parent / f".{slug}.publishing-{token}"
        retired = parent / f".{slug}.retired-{token}"
        try:
            parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(tiles_dir, staging)
            (staging / "metadata.json").write_text(
                json.dumps(metadata_document, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if target.exists():
                target.rename(retired)
            staging.rename(target)
        except OSError as exc:
            shutil.rmtree(staging, ignore_errors=True)
            # If the old copy was already moved aside, put it back so the
            # tile host keeps serving the previous version.
            if retired.exists() and not target.exists():
                try:
                    retired.rename(target)
                except OSError:
                    pass
            raise PublishError(f"Could not mirror tiles to {target}: {exc}") from exc
        shutil.rmtree(retired, ignore_errors=True)

    def rename(self, old_slug: str, new_slug: str) -> None:
        """Move the mirror when a dataset's slug changes. No-op if there is none."""
        old = self.published_dir_for(old_slug)
        new = self.published_dir_for(new_slug)
        if old is None or new is None or old == new or not old.is_dir():
            return
        try:
            if new.exists():
                shutil.rmtree(new)
            old.rename(new)
        except OSError as exc:
            raise PublishError(
                f"Could not rename published tiles {old} -> {new}: {exc}"
            ) from exc

    def unpublish(self, slug: str) -> None:
        """Remove the mirror for `slug`. Silent if mirroring is off or nothing is there."""
        try:
            target = self.published_dir_for(slug)
        except PublishError:
            return
        if target is not None and target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

    # -- publish ------------------------------------------------------------

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

        # Mirror first: if the tile host cannot be written, nothing is
        # recorded as published and the retry endpoint can simply run again.
        self._mirror(slug, tiles_dir, document)

        try:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            raise PublishError(f"Could not write metadata.json: {exc}") from exc

        return PublishResult(url_template, metadata_path, validation)
