"""Tile output validation (PRD §13).

A job may only report success once the pyramid on disk is actually usable.
Every check is collected rather than short-circuited, so the log names every
problem at once instead of one per re-run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["ValidationResult", "validate_tile_output", "validate_bounds"]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
WEBMERCATOR_MAX_LAT = 85.05112878


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    tile_count: int = 0
    zoom_levels: list[int] = field(default_factory=list)
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "tile_count": self.tile_count,
            "zoom_levels": self.zoom_levels,
            "size_bytes": self.size_bytes,
        }


def _is_readable_image(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return head.startswith(PNG_MAGIC) or head.startswith(JPEG_MAGIC)


def validate_tile_output(tiles_dir: Path, min_zoom: int, max_zoom: int) -> ValidationResult:
    """Check that a generated pyramid exists, covers the requested zooms, and
    contains at least one genuinely readable tile."""
    errors: list[str] = []
    tiles_dir = Path(tiles_dir)

    if not tiles_dir.is_dir():
        return ValidationResult(
            ok=False, errors=[f"Tile directory was not created: {tiles_dir}"]
        )

    present: list[int] = []
    for child in tiles_dir.iterdir():
        if child.is_dir() and child.name.isdigit():
            present.append(int(child.name))
    present.sort()

    missing = [z for z in range(min_zoom, max_zoom + 1) if z not in present]
    if missing:
        errors.append(
            "Zoom level(s) missing from the output: "
            + ", ".join(str(z) for z in missing)
        )

    tile_count = 0
    size_bytes = 0
    first_tile: Path | None = None
    for p in tiles_dir.rglob("*.png"):
        if first_tile is None:
            first_tile = p
        try:
            size_bytes += p.stat().st_size
        except OSError:
            continue
        tile_count += 1

    if tile_count == 0:
        errors.append("No tiles were produced.")
    elif first_tile is not None and not _is_readable_image(first_tile):
        errors.append(f"Generated tiles are not readable images (checked {first_tile.name}).")

    return ValidationResult(
        ok=not errors,
        errors=errors,
        tile_count=tile_count,
        zoom_levels=present,
        size_bytes=size_bytes,
    )


def validate_bounds(bounds: tuple[float, float, float, float] | None) -> list[str]:
    """Check WGS84 bounds are finite, ordered, and inside Web Mercator limits."""
    if bounds is None:
        return ["Raster bounds could not be determined."]
    errors: list[str] = []
    min_lon, min_lat, max_lon, max_lat = bounds

    values = [min_lon, min_lat, max_lon, max_lat]
    if any(v != v or v in (float("inf"), float("-inf")) for v in values):
        return ["Raster bounds contain non-finite values."]

    if min_lon >= max_lon or min_lat >= max_lat:
        errors.append("Raster bounds are degenerate (zero or negative extent).")
    if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        errors.append("Raster longitude falls outside -180..180.")
    if not (-WEBMERCATOR_MAX_LAT <= min_lat <= WEBMERCATOR_MAX_LAT
            and -WEBMERCATOR_MAX_LAT <= max_lat <= WEBMERCATOR_MAX_LAT):
        errors.append(
            f"Raster latitude falls outside the Web Mercator limit "
            f"(+/-{WEBMERCATOR_MAX_LAT})."
        )
    return errors
