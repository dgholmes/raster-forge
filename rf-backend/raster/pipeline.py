"""The GeoTIFF -> XYZ tile pipeline.

    validate -> [normalise NoData] -> gdal2tiles -> count

Progress is derived from GDAL's own dotted ruler. Both `gdal_translate` and
`gdal2tiles` emit `0...10...20...` with no trailing newline until the phase
completes, and gdal2tiles announces its phase on *stderr* while the ruler
goes to *stdout* — so the runner merges the streams and reports partial
buffers (see gdal_runner.GdalRunner).
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .analysis import (
    DEFAULT_RESAMPLING,
    MAX_SUPPORTED_ZOOM,
    RESAMPLING_METHODS,
    NoDataMode,
    decide_nodata,
)
from .gdal_runner import GdalRunner, find_gdal_tool, gdal2tiles_argv
from .inspect import RasterInfo
from .joblog import JobLog

__all__ = [
    "TileParams",
    "PipelineResult",
    "PipelineError",
    "RulerProgress",
    "Gdal2TilesProgress",
    "run_tile_pipeline",
]

ProgressFn = Callable[[int, str], None]
CancelFn = Callable[[], bool]


class PipelineError(RuntimeError):
    """A pipeline step failed. The message is already human-readable."""


@dataclass
class TileParams:
    min_zoom: int
    max_zoom: int
    resampling: str = DEFAULT_RESAMPLING
    nodata_mode: NoDataMode = "auto"
    processes: int = 2

    def validated(self) -> "TileParams":
        """Re-check every value. These become GDAL arguments, so this is the
        boundary that keeps a malformed request from reaching a subprocess."""
        if not isinstance(self.min_zoom, int) or not isinstance(self.max_zoom, int):
            raise PipelineError("Zoom levels must be whole numbers.")
        if not (0 <= self.min_zoom <= MAX_SUPPORTED_ZOOM):
            raise PipelineError(f"Minimum zoom must be between 0 and {MAX_SUPPORTED_ZOOM}.")
        if not (0 <= self.max_zoom <= MAX_SUPPORTED_ZOOM):
            raise PipelineError(f"Maximum zoom must be between 0 and {MAX_SUPPORTED_ZOOM}.")
        if self.min_zoom > self.max_zoom:
            raise PipelineError("Minimum zoom cannot be greater than maximum zoom.")
        if self.resampling not in RESAMPLING_METHODS:
            raise PipelineError(
                f"Unsupported resampling '{self.resampling}'. "
                f"Choose one of: {', '.join(RESAMPLING_METHODS)}."
            )
        if self.nodata_mode not in ("auto", "preserve", "remove"):
            raise PipelineError("NoData handling must be auto, preserve or remove.")
        processes = max(1, min(16, int(self.processes)))
        return TileParams(
            min_zoom=self.min_zoom,
            max_zoom=self.max_zoom,
            resampling=self.resampling,
            nodata_mode=self.nodata_mode,
            processes=processes,
        )

    def to_dict(self) -> dict:
        return {
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "resampling": self.resampling,
            "nodata_mode": self.nodata_mode,
            "processes": self.processes,
        }


@dataclass
class PipelineResult:
    tiles_dir: Path
    working_tif: Path | None
    tile_count: int
    size_bytes: int
    min_zoom: int
    max_zoom: int
    normalised: bool
    nodata_reason: str
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Progress parsing
# --------------------------------------------------------------------------

class RulerProgress:
    """Parses GDAL's dotted percentage ruler: `0...10...20...100 - done.`

    Only accepts segments that are unambiguously a ruler. Without that guard,
    an ordinary warning such as
        "Warning 3: Cannot find tms_MapML_APSTILE.json"
    would yield "3" and slam the progress bar back to 3%.
    """

    # Only digits / dots / spaces, optionally trailing "- done.".
    #
    # The anchor is NOT "^0": gdal2tiles writes the ruler to stdout while
    # writing warnings to stderr, and when the two interleave mid-ruler the
    # leading "0" is swallowed into the preceding segment
    # ("0C:\\...\\gdal.py:311: FutureWarning: ..."), leaving the remainder as
    # "...10...20...100 - done.". Anchoring on "0" silently dropped every
    # such ruler and froze the progress bar.
    _RULER = re.compile(r"^[\d.\s]*\d[\d.\s]*(?:-\s*done\.?)?$", re.IGNORECASE)
    _NUM = re.compile(r"\d+")

    @classmethod
    def parse(cls, segment: str) -> int | None:
        """Percentage 0-100, or None if this is not a ruler."""
        text = (segment or "").strip()
        if not text or not cls._RULER.match(text):
            return None
        # A ruler is either the initial "0" or contains dot runs. Without this
        # a bare number on its own line would read as a percentage.
        if "..." not in text and text != "0":
            return None
        nums = cls._NUM.findall(text)
        if not nums:
            return None
        try:
            return max(0, min(100, int(nums[-1])))
        except ValueError:
            return None


class Gdal2TilesProgress:
    """Maps gdal2tiles' phases onto one overall percentage.

    gdal2tiles prints "Generating Base Tiles:" and a ruler, then "Generating
    Overview Tiles:" followed by **one ruler per overview zoom level** — each
    restarting at 0. Treating them as a single ruler makes the bar jump
    backwards (73% -> 71%), so the overview span is divided across the known
    number of passes and a restart advances to the next slice.

    Base gets 70% of the span because it reads the source imagery and
    dominates wall time; overviews only downsample what base produced.
    """

    BASE_FRACTION = 0.70

    def __init__(self, lo: int = 0, hi: int = 100, overview_passes: int = 1) -> None:
        self.lo = lo
        self.hi = hi
        self.overview_passes = max(1, overview_passes)
        self.phase: str | None = None
        self._pass_index = 0
        self._prev_pct = -1
        self._last_overall = lo
        self._last: tuple[int, str] | None = None

    def _span(self) -> tuple[float, float]:
        width = self.hi - self.lo
        split = self.lo + width * self.BASE_FRACTION
        return (self.lo, split) if self.phase != "overview" else (split, self.hi)

    def feed(self, segment: str) -> tuple[int, str] | None:
        """Feed one output segment. Returns (percent, step) when it changes."""
        text = (segment or "").strip()
        low = text.lower()

        if "generating base tiles" in low:
            self.phase = "base"
            self._prev_pct = -1
            return self._emit(0)
        if "generating overview tiles" in low:
            self.phase = "overview"
            self._pass_index = 0
            self._prev_pct = -1
            return self._emit(0)

        pct = RulerProgress.parse(text)
        if pct is None:
            return None
        if self.phase is None:
            # A ruler before any header — treat it as the base pass.
            self.phase = "base"

        # A ruler that restarts means gdal2tiles moved to the next zoom level.
        if self.phase == "overview" and pct < self._prev_pct:
            self._pass_index = min(self._pass_index + 1, self.overview_passes - 1)
        self._prev_pct = pct
        return self._emit(pct)

    def _emit(self, phase_pct: int) -> tuple[int, str] | None:
        start, end = self._span()
        if self.phase == "overview":
            slice_width = (end - start) / self.overview_passes
            position = start + slice_width * (self._pass_index + phase_pct / 100.0)
            label = f"Generating overview tiles ({phase_pct}%)"
        else:
            position = start + (end - start) * (phase_pct / 100.0)
            label = f"Generating base tiles ({phase_pct}%)"

        overall = int(round(position))
        # Progress must never go backwards, whatever GDAL prints.
        overall = max(overall, self._last_overall)
        self._last_overall = overall

        result = (overall, label)
        if result == self._last:
            return None
        self._last = result
        return result


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def _count_tiles(tiles_dir: Path) -> tuple[int, int]:
    """(tile count, total bytes) under a tile pyramid."""
    count = 0
    size = 0
    for p in tiles_dir.rglob("*.png"):
        try:
            size += p.stat().st_size
            count += 1
        except OSError:
            continue
    return count, size


def run_tile_pipeline(
    source: Path,
    working_dir: Path,
    tiles_dir: Path,
    params: TileParams,
    info: RasterInfo,
    log: JobLog,
    progress: ProgressFn,
    runner: GdalRunner,
    should_cancel: CancelFn | None = None,
    timeout: int | None = None,
) -> PipelineResult:
    """Run the full GeoTIFF -> XYZ pipeline.

    `runner` is supplied by the caller so a cancel request can terminate the
    live subprocess. `progress` receives (percent, step_label).
    """
    params = params.validated()
    should_cancel = should_cancel or (lambda: False)
    warnings: list[str] = []

    def check_cancel() -> None:
        if should_cancel():
            runner.cancel()

    progress(2, "Validating raster")
    if info.epsg is None and not info.crs_name:
        raise PipelineError(
            "This raster has no coordinate reference system, so it cannot be "
            "placed on a web map. Re-export it with projection metadata, or "
            "assign a CRS before uploading."
        )
    if not info.bounds_wgs84:
        warnings.append(
            "Could not determine WGS84 bounds from the source; the preview may "
            "not auto-fit to the imagery."
        )
        log.warn("validate", warnings[-1])

    # -- 1. NoData normalisation -----------------------------------------
    decision = decide_nodata(info, params.nodata_mode)
    log.info("nodata", decision.reason)
    if decision.warning:
        log.warn("nodata", decision.warning)
        warnings.append(decision.warning)

    tile_input = source
    working_tif: Path | None = None

    if decision.normalise:
        check_cancel()
        working_dir.mkdir(parents=True, exist_ok=True)
        working_tif = working_dir / "clean.tif"
        argv = [
            str(find_gdal_tool("gdal_translate")),
            str(source),
            str(working_tif),
            "-a_nodata", "none",
            "-co", "TILED=YES",
            "-co", "COMPRESS=DEFLATE",
        ]
        log.command("translate", argv)
        progress(5, "Normalising raster")

        translate_progress = Gdal2TilesProgress(lo=5, hi=15)
        translate_progress.phase = "base"  # gdal_translate has a single ruler

        def on_translate_partial(seg: str) -> None:
            pct = RulerProgress.parse(seg)
            if pct is not None:
                progress(5 + int(round(pct / 100.0 * 10)), "Normalising raster")

        def on_translate_line(seg: str) -> None:
            on_translate_partial(seg)
            if RulerProgress.parse(seg) is None:
                log.info("translate", seg)

        code = runner.run(
            argv, on_line=on_translate_line, on_partial=on_translate_partial, timeout=timeout
        )
        if code != 0:
            raise PipelineError(
                "Could not create a NoData-normalised copy of the raster. "
                "See the technical log for GDAL's output."
            )
        if not working_tif.is_file():
            raise PipelineError("Normalisation reported success but produced no file.")
        tile_input = working_tif
        log.info("translate", f"Wrote normalised copy ({working_tif.stat().st_size:,} bytes)")

    # -- 2. Tile generation ----------------------------------------------
    check_cancel()
    tiles_dir.mkdir(parents=True, exist_ok=True)
    argv = gdal2tiles_argv() + [
        "--profile=mercator",
        "-z", f"{params.min_zoom}-{params.max_zoom}",
        "--xyz",
        "-r", params.resampling,
        f"--processes={params.processes}",
        str(tile_input),
        str(tiles_dir),
    ]
    log.command("tiles", argv)
    progress(15, "Generating tiles")

    # gdal2tiles emits one overview ruler per zoom level below the max.
    tracker = Gdal2TilesProgress(
        lo=15, hi=95, overview_passes=max(1, params.max_zoom - params.min_zoom)
    )

    def on_tiles_partial(seg: str) -> None:
        update = tracker.feed(seg)
        if update:
            progress(update[0], update[1])

    def on_tiles_line(seg: str) -> None:
        update = tracker.feed(seg)
        if update:
            progress(update[0], update[1])
        else:
            # Not a ruler and not a phase header: real output worth logging.
            if RulerProgress.parse(seg) is None:
                log.info("tiles", seg)

    code = runner.run(
        argv, on_line=on_tiles_line, on_partial=on_tiles_partial, timeout=timeout
    )
    if code != 0:
        raise PipelineError(
            "Tile generation failed. See the technical log for GDAL's output."
        )

    # -- 3. Count --------------------------------------------------------
    progress(96, "Counting tiles")
    tile_count, size_bytes = _count_tiles(tiles_dir)
    if tile_count == 0:
        raise PipelineError(
            "Tile generation completed but produced no tiles. The raster's "
            "footprint may fall outside the requested zoom range."
        )
    log.info("tiles", f"Generated {tile_count:,} tiles ({size_bytes:,} bytes)")

    return PipelineResult(
        tiles_dir=tiles_dir,
        working_tif=working_tif,
        tile_count=tile_count,
        size_bytes=size_bytes,
        min_zoom=params.min_zoom,
        max_zoom=params.max_zoom,
        normalised=decision.normalise,
        nodata_reason=decision.reason,
        warnings=warnings,
    )


def cleanup_working(working_dir: Path) -> None:
    """Remove intermediate files. Kept separate so a failed job's working
    copy survives for inspection."""
    shutil.rmtree(working_dir, ignore_errors=True)
