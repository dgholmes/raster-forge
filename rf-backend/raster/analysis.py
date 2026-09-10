"""Raster analysis — the two judgement calls RasterForge makes for the user.

1. Whether a raster's NoData metadata must be stripped before tiling.
2. What maximum zoom the source resolution actually supports.

Both are pure functions of a RasterInfo so they can be unit-tested without
GDAL and reused by the API (to show a recommendation) and the worker (to
build the pipeline).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .inspect import EARTH_EQUATORIAL_M_PER_PX_Z0, RasterInfo

__all__ = [
    "NoDataMode",
    "NoDataDecision",
    "RESAMPLING_METHODS",
    "DEFAULT_RESAMPLING",
    "MAX_SUPPORTED_ZOOM",
    "decide_nodata",
    "native_zoom_for_resolution",
    "recommend_max_zoom",
    "estimate_tile_count",
]

NoDataMode = Literal["auto", "preserve", "remove"]

RESAMPLING_METHODS = ("nearest", "bilinear", "cubic", "cubicspline", "lanczos")
DEFAULT_RESAMPLING = "bilinear"
MAX_SUPPORTED_ZOOM = 22

# The exact warning the PRD (§8.2) specifies for the known failure mode.
ALPHA_NODATA_WARNING = (
    "This image contains an Alpha band and also defines 0 as NoData. "
    "Valid zero-value pixels may be interpreted as transparent during processing."
)


@dataclass
class NoDataDecision:
    normalise: bool
    reason: str
    warning: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"normalise": self.normalise, "reason": self.reason, "warning": self.warning}


def _has_risky_nodata(info: RasterInfo) -> bool:
    """The condition that silently corrupts orthomosaic tiling: an Alpha band
    carrying transparency AND 0 declared as NoData, so every legitimately
    black pixel is also treated as absent data."""
    return info.has_alpha and any(nd == 0 for nd in info.nodata_values if nd is not None)


def decide_nodata(info: RasterInfo, mode: NoDataMode = "auto") -> NoDataDecision:
    """Decide whether to write a NoData-stripped working copy before tiling.

    The warning is attached whenever the risky condition holds, regardless of
    the chosen mode — the user should see the risk even when overriding it.
    """
    risky = _has_risky_nodata(info)
    warning = ALPHA_NODATA_WARNING if risky else None

    if mode == "preserve":
        return NoDataDecision(
            normalise=False,
            reason="Source NoData preserved at the user's request.",
            warning=warning,
        )

    if mode == "remove":
        return NoDataDecision(
            normalise=True,
            reason="NoData metadata removal requested explicitly.",
            warning=warning,
        )

    # auto
    if risky:
        return NoDataDecision(
            normalise=True,
            reason=(
                "Alpha band present and NoData=0 — removing NoData metadata so "
                "valid black pixels are not treated as transparent."
            ),
            warning=warning,
        )
    if any(nd is not None for nd in info.nodata_values) and not info.has_alpha:
        return NoDataDecision(
            normalise=False,
            reason=(
                "NoData is defined but there is no Alpha band, so NoData is the "
                "only transparency signal — preserving it."
            ),
        )
    return NoDataDecision(
        normalise=False,
        reason="No conflicting NoData configuration detected — tiling the source directly.",
    )


def native_zoom_for_resolution(gsd_m: float, lat: float) -> int:
    """The Web Mercator zoom whose ground resolution most closely matches `gsd_m`.

        res(z, lat) = 156543.03392804097 * cos(lat) / 2^z
        z_native    = round( log2( 156543.03392804097 * cos(lat) / gsd_m ) )

    Rounds to *nearest*, deliberately. Truncating would stop a 6.8 cm
    orthomosaic at z20, whose 0.118 m/px is 1.74x coarser than the source —
    discarding real detail. Rounding up would push a 30 m raster to z13 and
    upscale it 2x. Nearest gives 21 and 12 respectively, which is what an
    operator means by "the zoom this imagery actually supports".
    """
    if gsd_m is None or gsd_m <= 0:
        return MAX_SUPPORTED_ZOOM
    lat = max(-85.0, min(85.0, lat))
    metres_per_px_z0 = EARTH_EQUATORIAL_M_PER_PX_Z0 * math.cos(math.radians(lat))
    if metres_per_px_z0 <= 0:
        return MAX_SUPPORTED_ZOOM
    z = math.log2(metres_per_px_z0 / gsd_m)
    # floor(z + 0.5) rather than round(), which uses banker's rounding.
    return max(0, min(MAX_SUPPORTED_ZOOM, math.floor(z + 0.5)))


def recommend_max_zoom(info: RasterInfo) -> int | None:
    """Recommended maximum zoom for this raster, or None if it cannot be judged."""
    if not info.gsd_m or info.gsd_m <= 0:
        return None
    lat = info.center_wgs84[1] if info.center_wgs84 else 0.0
    return native_zoom_for_resolution(info.gsd_m, lat)


def estimate_tile_count(info: RasterInfo, min_zoom: int, max_zoom: int) -> int:
    """Rough tile count for the requested zoom span — used for the disk
    pre-check, not for reporting. Derived from the raster's WGS84 footprint
    projected onto the Web Mercator tile grid at each zoom."""
    if not info.bounds_wgs84:
        return 0
    min_lon, min_lat, max_lon, max_lat = info.bounds_wgs84
    total = 0
    for z in range(max(0, min_zoom), min(MAX_SUPPORTED_ZOOM, max_zoom) + 1):
        n = 2 ** z
        x0, x1 = _lon_to_tile_x(min_lon, n), _lon_to_tile_x(max_lon, n)
        y0, y1 = _lat_to_tile_y(max_lat, n), _lat_to_tile_y(min_lat, n)
        total += max(1, abs(x1 - x0) + 1) * max(1, abs(y1 - y0) + 1)
    return total


def _lon_to_tile_x(lon: float, n: int) -> int:
    return int(max(0, min(n - 1, math.floor((lon + 180.0) / 360.0 * n))))


def _lat_to_tile_y(lat: float, n: int) -> int:
    lat = max(-85.05112878, min(85.05112878, lat))
    rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * n
    return int(max(0, min(n - 1, math.floor(y))))
