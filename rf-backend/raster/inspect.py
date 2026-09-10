"""Raster inspection — `gdalinfo -json` parsed into a typed RasterInfo.

We parse the JSON output rather than scraping gdalinfo's human-readable text:
the text layout is a presentation format that shifts between GDAL releases,
while `-json` is a documented structure. `parse_gdalinfo()` is pure, so the
whole parser is unit-testable without GDAL installed.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .gdal_runner import GdalRunner, find_gdal_tool

__all__ = [
    "BandInfo",
    "RasterInfo",
    "RasterInspectionError",
    "inspect_raster",
    "parse_gdalinfo",
]

# Metres per pixel at zoom 0 on the equator (Web Mercator, 256px tiles).
EARTH_EQUATORIAL_M_PER_PX_Z0 = 156543.03392804097
# Metres per degree of longitude at the equator.
METRES_PER_DEGREE = 111319.49079327358


class RasterInspectionError(RuntimeError):
    """gdalinfo failed or returned something we cannot use."""


@dataclass
class BandInfo:
    index: int
    dtype: str
    color_interp: str
    nodata: float | None
    is_alpha: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RasterInfo:
    driver: str
    width: int
    height: int
    band_count: int
    crs_name: str | None
    epsg: int | None
    pixel_size_x: float
    pixel_size_y: float
    gsd_m: float | None
    bounds_wgs84: tuple[float, float, float, float] | None  # (minlon, minlat, maxlon, maxlat)
    center_wgs84: tuple[float, float] | None                # (lon, lat)
    has_alpha: bool
    nodata_values: list[float | None]
    bands: list[BandInfo]
    is_geographic: bool
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "driver": self.driver,
            "width": self.width,
            "height": self.height,
            "band_count": self.band_count,
            "crs_name": self.crs_name,
            "epsg": self.epsg,
            "pixel_size_x": self.pixel_size_x,
            "pixel_size_y": self.pixel_size_y,
            "gsd_m": self.gsd_m,
            "bounds_wgs84": list(self.bounds_wgs84) if self.bounds_wgs84 else None,
            "center_wgs84": list(self.center_wgs84) if self.center_wgs84 else None,
            "has_alpha": self.has_alpha,
            "nodata_values": self.nodata_values,
            "bands": [b.to_dict() for b in self.bands],
            "is_geographic": self.is_geographic,
        }
        if include_raw:
            d["raw"] = self.raw
        return d


# --------------------------------------------------------------------------
# WKT / CRS helpers
# --------------------------------------------------------------------------

_CRS_NAME_RE = re.compile(
    r'^\s*(?:PROJCRS|GEOGCRS|PROJCS|GEOGCS|COMPOUNDCRS|BOUNDCRS)\s*\[\s*"([^"]+)"'
)
_EPSG_RE = re.compile(r'(?:AUTHORITY|ID)\s*\[\s*"EPSG"\s*,\s*"?(\d+)"?\s*\]', re.IGNORECASE)
_LENGTH_UNIT_RE = re.compile(
    r'(?:LENGTHUNIT|UNIT)\s*\[\s*"([^"]+)"\s*,\s*([0-9.eE+-]+)', re.IGNORECASE
)


def _crs_name_from_wkt(wkt: str) -> str | None:
    m = _CRS_NAME_RE.match(wkt or "")
    return m.group(1) if m else None


def _epsg_from_wkt(wkt: str) -> int | None:
    """Last EPSG authority in the WKT — the outermost CRS, not a nested datum."""
    matches = _EPSG_RE.findall(wkt or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except (TypeError, ValueError):
        return None


def _is_geographic_wkt(wkt: str) -> bool:
    return bool(re.match(r'^\s*(?:GEOGCRS|GEOGCS)\s*\[', wkt or ""))


def _linear_unit_factor(wkt: str) -> float:
    """Metres per CRS linear unit. 1.0 for metre, 0.3048 for foot, etc."""
    for name, factor in _LENGTH_UNIT_RE.findall(wkt or ""):
        low = name.lower()
        if low in ("degree", "radian", "grad"):
            continue
        try:
            f = float(factor)
        except (TypeError, ValueError):
            continue
        if f > 0:
            return f
    return 1.0


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _bounds_from_wgs84_extent(extent: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not extent:
        return None
    coords = extent.get("coordinates")
    points: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if (
            isinstance(node, (list, tuple))
            and len(node) == 2
            and all(isinstance(v, (int, float)) for v in node)
        ):
            points.append((float(node[0]), float(node[1])))
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(coords)
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lons), min(lats), max(lons), max(lats))


def _bounds_from_corners(corners: dict[str, Any] | None) -> tuple[float, float, float, float] | None:
    """Fallback when wgs84Extent is absent — only valid if the CRS is already
    geographic; the caller decides whether to trust it."""
    if not corners:
        return None
    pts = [corners.get(k) for k in ("upperLeft", "lowerLeft", "upperRight", "lowerRight")]
    vals = [p for p in pts if isinstance(p, (list, tuple)) and len(p) == 2]
    if not vals:
        return None
    lons = [float(p[0]) for p in vals]
    lats = [float(p[1]) for p in vals]
    return (min(lons), min(lats), max(lons), max(lats))


def parse_gdalinfo(data: dict[str, Any]) -> RasterInfo:
    """Turn a `gdalinfo -json` dict into a RasterInfo. Pure — no I/O."""
    size = data.get("size") or [0, 0]
    width = int(size[0]) if len(size) > 0 else 0
    height = int(size[1]) if len(size) > 1 else 0

    cs = data.get("coordinateSystem") or {}
    wkt = cs.get("wkt") or ""
    crs_name = _crs_name_from_wkt(wkt)
    is_geographic = _is_geographic_wkt(wkt)

    epsg: int | None = None
    stac = data.get("stac") or {}
    if isinstance(stac.get("proj:epsg"), int):
        epsg = stac["proj:epsg"]
    if epsg is None:
        ident = cs.get("id") or {}
        code = ident.get("code")
        if isinstance(code, int):
            epsg = code
        elif isinstance(code, str) and code.isdigit():
            epsg = int(code)
    if epsg is None:
        epsg = _epsg_from_wkt(wkt)

    gt = data.get("geoTransform") or []
    pixel_size_x = abs(float(gt[1])) if len(gt) > 5 else 0.0
    pixel_size_y = abs(float(gt[5])) if len(gt) > 5 else 0.0

    bands: list[BandInfo] = []
    for raw_band in data.get("bands") or []:
        interp = raw_band.get("colorInterpretation") or "Undefined"
        nodata = raw_band.get("noDataValue")
        try:
            nodata_val = float(nodata) if nodata is not None else None
        except (TypeError, ValueError):
            nodata_val = None
        bands.append(
            BandInfo(
                index=int(raw_band.get("band", len(bands) + 1)),
                dtype=raw_band.get("type") or "Unknown",
                color_interp=interp,
                nodata=nodata_val,
                is_alpha=interp.lower() == "alpha",
            )
        )

    bounds = _bounds_from_wgs84_extent(data.get("wgs84Extent"))
    if bounds is None and is_geographic:
        bounds = _bounds_from_corners(data.get("cornerCoordinates"))

    center: tuple[float, float] | None = None
    if bounds is not None:
        center = ((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)

    # Ground sample distance in metres. Projected CRS: pixel size scaled by the
    # CRS's linear unit. Geographic CRS: degrees converted at the centre latitude.
    gsd_m: float | None = None
    if pixel_size_x > 0:
        if is_geographic:
            lat = center[1] if center else 0.0
            gsd_m = pixel_size_x * METRES_PER_DEGREE * math.cos(math.radians(lat))
        else:
            gsd_m = pixel_size_x * _linear_unit_factor(wkt)

    return RasterInfo(
        driver=data.get("driverShortName") or data.get("driver") or "Unknown",
        width=width,
        height=height,
        band_count=len(bands),
        crs_name=crs_name,
        epsg=epsg,
        pixel_size_x=pixel_size_x,
        pixel_size_y=pixel_size_y,
        gsd_m=gsd_m,
        bounds_wgs84=bounds,
        center_wgs84=center,
        has_alpha=any(b.is_alpha for b in bands),
        nodata_values=[b.nodata for b in bands],
        bands=bands,
        is_geographic=is_geographic,
        raw=data,
    )


def inspect_raster(path: Path, timeout: int = 300) -> RasterInfo:
    """Run `gdalinfo -json` against `path` and parse the result."""
    tool = find_gdal_tool("gdalinfo")
    code, out = GdalRunner().run_capture(
        [str(tool), "-json", "-noct", str(path)], timeout=timeout
    )
    if code != 0:
        raise RasterInspectionError(out.strip() or f"gdalinfo exited with code {code}")

    # run_capture strips per-segment whitespace, which is harmless for JSON,
    # but GDAL may print warnings before the document — start at the first '{'.
    start = out.find("{")
    if start == -1:
        raise RasterInspectionError(f"gdalinfo produced no JSON document:\n{out.strip()}")
    try:
        data = json.loads(out[start:])
    except json.JSONDecodeError as exc:
        raise RasterInspectionError(f"Could not parse gdalinfo JSON: {exc}") from exc

    info = parse_gdalinfo(data)
    if info.width <= 0 or info.height <= 0:
        raise RasterInspectionError("Raster reports zero width or height.")
    return info
