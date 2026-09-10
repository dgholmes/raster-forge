"""Error codes and GDAL error translation (PRD §15, §21).

GDAL's raw output is never what the user reads. Every failure maps to a code
with an explanation that says what to actually do about it; the technical log
stays one click away in the UI.
"""
from __future__ import annotations

import re

__all__ = ["ERROR_MESSAGES", "classify_gdal_error", "api_error"]

ERROR_MESSAGES: dict[str, str] = {
    "unsupported_file": (
        "That file is not a GeoTIFF. RasterForge accepts .tif and .tiff rasters."
    ),
    "corrupted_raster": (
        "The file could not be read as a raster. It may be truncated, or it may "
        "not be a GeoTIFF despite its extension."
    ),
    "missing_crs": (
        "GDAL could not determine the source coordinate system. Check that your "
        "GeoTIFF contains valid projection metadata."
    ),
    "invalid_bounds": (
        "The raster's geographic bounds are invalid or fall outside the Web "
        "Mercator limits, so it cannot be placed on a web map."
    ),
    "invalid_nodata": (
        "The raster's NoData configuration could not be applied. Try the "
        "'Remove NoData metadata' option."
    ),
    "insufficient_disk": (
        "There is not enough free disk space to complete this job. Free up space "
        "or delete unused datasets, then run the job again."
    ),
    "insufficient_memory": (
        "Processing ran out of memory. Try a smaller zoom range, or process this "
        "raster when fewer jobs are running."
    ),
    "gdal_failure": (
        "The GDAL process failed. See the technical log for its output."
    ),
    "cancelled": "The job was cancelled.",
    "validation_failed": (
        "Tile generation finished but the output failed validation, so it was "
        "not published. See the technical log for details."
    ),
    "publish_failed": (
        "The tiles were generated successfully but publishing failed. You can "
        "retry publishing without re-running the raster processing."
    ),
    "permission_denied": "You do not have permission to perform this action.",
    "transfer_failed": "Transferring the generated tiles to the tile server failed.",
    "packaging_failed": (
        "The download archive could not be built. This is usually a disk space "
        "problem."
    ),
    "not_found": "That item does not exist.",
    "invalid_request": "The request was not valid.",
    "raster_too_large": (
        "This raster exceeds the configured size limit for this server."
    ),
    "job_conflict": "A job is already running for this dataset.",
    "gdal_missing": (
        "GDAL is not available on this server. An administrator needs to install "
        "QGIS (which bundles gdal2tiles) or set GDAL_ROOT."
    ),
}

# Ordered: the first pattern that matches wins, so specific beats general.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"no space left|not enough space|WinError 112|disk full", re.I),
     "insufficient_disk"),
    (re.compile(r"memoryerror|cannot allocate|out of memory|bad_alloc", re.I),
     "insufficient_memory"),
    (re.compile(
        r"does not have a spatial reference|no spatial reference|"
        r"unable to compute a transformation|cannot find coordinate operations|"
        r"georeference|not georeferenced", re.I),
     "missing_crs"),
    (re.compile(
        r"not recognized as (?:being in )?a supported file format|"
        r"unable to open|no such file|corrupt|premature end|"
        r"tifffetchdirectory|not a tiff", re.I),
     "corrupted_raster"),
    (re.compile(r"permission denied|access is denied|WinError 5", re.I),
     "permission_denied"),
    (re.compile(r"nodata", re.I), "invalid_nodata"),
]


def classify_gdal_error(text: str | None) -> tuple[str, str]:
    """Map GDAL/pipeline output to (error_code, human message)."""
    if not text:
        return "gdal_failure", ERROR_MESSAGES["gdal_failure"]

    for pattern, code in _PATTERNS:
        if pattern.search(text):
            return code, ERROR_MESSAGES[code]

    return "gdal_failure", ERROR_MESSAGES["gdal_failure"]


def api_error(code: str, status: int = 400, detail: str | None = None) -> tuple[dict, int]:
    """Uniform error body: every failure carries a machine code and prose."""
    return (
        {
            "error_code": code,
            "error": detail or ERROR_MESSAGES.get(code, "Something went wrong."),
        },
        status,
    )
