"""Phase-0 harness — run the raster pipeline without the web application.

    python -m raster.cli doctor
    python -m raster.cli inspect <input.tif>
    python -m raster.cli tile <input.tif> <outdir> --min 14 --max 21

Exists so the processing engine can be proven against real orthomosaics
before any API, queue or UI is involved (PRD §36, Phase 0).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .analysis import (
    DEFAULT_RESAMPLING,
    RESAMPLING_METHODS,
    decide_nodata,
    estimate_tile_count,
    recommend_max_zoom,
)
from .gdal_runner import GdalNotFound, GdalRunner, gdal_diagnostics
from .inspect import RasterInfo, RasterInspectionError, inspect_raster
from .joblog import JobLog
from .pipeline import PipelineError, TileParams, run_tile_pipeline
from .validate import validate_bounds, validate_tile_output


def _fmt_int(n: float | int | None) -> str:
    return f"{n:,}" if isinstance(n, (int, float)) else "—"


def print_info(info: RasterInfo) -> None:
    gsd_cm = f"{info.gsd_m * 100:.1f} cm/pixel" if info.gsd_m else "—"
    rec = recommend_max_zoom(info)

    print()
    print(f"  {'Driver':<14}{info.driver}")
    print(f"  {'CRS':<14}{info.crs_name or '(none)'}")
    print(f"  {'EPSG':<14}{info.epsg if info.epsg else '(none)'}")
    print(f"  {'Dimensions':<14}{_fmt_int(info.width)} x {_fmt_int(info.height)} px")
    print(f"  {'Pixel Size':<14}{info.pixel_size_x:g} x {info.pixel_size_y:g}")
    print(f"  {'Approx. GSD':<14}{gsd_cm}")
    if info.bounds_wgs84:
        w, s, e, n = info.bounds_wgs84
        print(f"  {'Bounds':<14}{w:.6f}, {s:.6f}  ->  {e:.6f}, {n:.6f}")
    if info.center_wgs84:
        print(f"  {'Center':<14}{info.center_wgs84[0]:.6f}, {info.center_wgs84[1]:.6f}")
    print(f"  {'Bands':<14}{info.band_count}")
    print()
    for b in info.bands:
        nodata = "—" if b.nodata is None else f"{b.nodata:g}"
        print(f"    Band {b.index:<3}{b.color_interp:<10}{b.dtype:<8}NoData: {nodata}")
    print()

    for err in validate_bounds(info.bounds_wgs84):
        print(f"  [!] {err}")

    decision = decide_nodata(info, "auto")
    if decision.warning:
        print(f"  [!] {decision.warning}")
    print(f"  Auto NoData handling: "
          f"{'normalise (write clean copy)' if decision.normalise else 'use source as-is'}")
    print(f"      {decision.reason}")

    if rec is not None:
        print(f"  Recommended maximum zoom: {rec}")
        print(f"      Zoom {rec + 1} and above would upscale the source imagery.")
    print()


def cmd_doctor(_: argparse.Namespace) -> int:
    print("\nGDAL environment\n" + "-" * 60)
    for key, value in gdal_diagnostics().items():
        print(f"  {key:<16}{value}")
    print()
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.input).resolve()
    if not path.is_file():
        print(f"error: no such file: {path}", file=sys.stderr)
        return 2
    print(f"\n{path.name}  ({path.stat().st_size:,} bytes)")
    print("-" * 60)
    info = inspect_raster(path)
    print_info(info)
    return 0


def cmd_tile(args: argparse.Namespace) -> int:
    src = Path(args.input).resolve()
    if not src.is_file():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 2

    outdir = Path(args.outdir).resolve()
    working = outdir / "working"
    tiles = outdir / "tiles"
    logs = outdir / "logs"
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"\n{src.name}")
    print("-" * 60)
    info = inspect_raster(src)
    print_info(info)

    max_zoom = args.max
    if max_zoom is None:
        max_zoom = recommend_max_zoom(info) or 18
        print(f"  Using recommended maximum zoom: {max_zoom}")

    params = TileParams(
        min_zoom=args.min,
        max_zoom=max_zoom,
        resampling=args.resampling,
        nodata_mode=args.nodata,
        processes=args.processes,
    )
    est = estimate_tile_count(info, params.min_zoom, params.max_zoom)
    print(f"  Estimated tiles: ~{est:,}")
    print()

    log = JobLog(logs / "phase0.log")
    runner = GdalRunner()
    started = time.monotonic()
    last_render = [0.0]

    def progress(pct: int, step: str) -> None:
        now = time.monotonic()
        if now - last_render[0] < 0.1 and pct < 100:
            return
        last_render[0] = now
        filled = int(pct / 100 * 34)
        bar = "#" * filled + "-" * (34 - filled)
        elapsed = time.strftime("%H:%M:%S", time.gmtime(now - started))
        sys.stdout.write(f"\r  [{bar}] {pct:3d}%  {elapsed}  {step[:38]:<38}")
        sys.stdout.flush()

    try:
        result = run_tile_pipeline(
            source=src,
            working_dir=working,
            tiles_dir=tiles,
            params=params,
            info=info,
            log=log,
            progress=progress,
            runner=runner,
        )
    except (PipelineError, GdalNotFound, RasterInspectionError) as exc:
        print()
        print(f"\n  FAILED: {exc}\n")
        print(f"  Technical log: {log.path}")
        return 1
    except KeyboardInterrupt:
        runner.cancel()
        print("\n\n  Cancelled.\n")
        return 130

    progress(100, "Done")
    print("\n")

    validation = validate_tile_output(tiles, result.min_zoom, result.max_zoom)
    print(f"  Tiles        {result.tile_count:,}")
    print(f"  Size         {result.size_bytes / 1_048_576:.1f} MB")
    print(f"  Zoom levels  {validation.zoom_levels}")
    print(f"  Normalised   {'yes' if result.normalised else 'no'}")
    print(f"  Validation   {'PASS' if validation.ok else 'FAIL'}")
    for err in validation.errors:
        print(f"    [!] {err}")
    for warn in result.warnings:
        print(f"    [!] {warn}")
    print(f"  Output       {tiles}")
    print(f"  Log          {log.path}")
    print()
    return 0 if validation.ok else 1


def _force_utf8_console() -> None:
    """Korean Windows consoles default to cp949, which cannot encode an em-dash
    (or most of what a Korean dataset name contains). Without this, printing a
    perfectly good message raises UnicodeEncodeError and kills the command."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    parser = argparse.ArgumentParser(
        prog="raster.cli", description="RasterForge processing harness"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="show the resolved GDAL environment").set_defaults(
        func=cmd_doctor
    )

    p_inspect = sub.add_parser("inspect", help="parse and print raster metadata")
    p_inspect.add_argument("input")
    p_inspect.set_defaults(func=cmd_inspect)

    p_tile = sub.add_parser("tile", help="generate an XYZ tile pyramid")
    p_tile.add_argument("input")
    p_tile.add_argument("outdir")
    p_tile.add_argument("--min", type=int, default=14, help="minimum zoom (default 14)")
    p_tile.add_argument("--max", type=int, default=None, help="maximum zoom (default: recommended)")
    p_tile.add_argument("--resampling", choices=RESAMPLING_METHODS, default=DEFAULT_RESAMPLING)
    p_tile.add_argument("--nodata", choices=("auto", "preserve", "remove"), default="auto")
    p_tile.add_argument("--processes", type=int, default=2)
    p_tile.set_defaults(func=cmd_tile)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GdalNotFound as exc:
        print(f"\nGDAL is not usable: {exc}\n", file=sys.stderr)
        return 3
    except RasterInspectionError as exc:
        print(f"\nCould not read the raster: {exc}\n", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
