# RasterForge MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a web platform where an operator uploads a GeoTIFF and gets published, previewable XYZ tiles at a copyable URL — with no OSGeo4W, no typed GDAL command, and no SCP.

**Architecture:** A Flask API owns datasets, jobs and publishing; a bounded in-process worker pool runs a GDAL pipeline (`gdalinfo` -> optional `gdal_translate` -> `gdal2tiles`) whose state lives in the database, not the queue; tiles are served directly out of the directory they were generated into. The frontend is the lab's `map-dashboard-starter` shell (Vite + React + TS + Leaflet) with its domain layer replaced by RasterForge's dataset/job screens.

**Tech Stack:** Python 3.11 · Flask 3.1 · Flask-SQLAlchemy · Flask-JWT-Extended · Flask-SocketIO (threading) · GDAL 3.10/3.11 via QGIS · SQLite (Postgres-ready) · Vite 5 · React 18 · TypeScript 5.4 · Leaflet 1.9 · react-leaflet 4 · lucide-react

**Spec:** [`docs/PRD.md`](./PRD.md)

---

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include this section.

- **GDAL binaries resolve in this order:** explicit env (`GDAL_BIN_DIR`, `GDAL2TILES_PATH`) -> QGIS install -> OSGeo4W -> PATH. On this machine `gdal2tiles.exe` exists **only** under `C:\Program Files\QGIS 3.42.2\apps\Python312\Scripts`.
- **`GDAL_DATA` and `PROJ_LIB` must be injected into every GDAL subprocess.** Without `GDAL_DATA`, `gdal2tiles` emits `Warning 3: Cannot find tms_MapML_APSTILE.json`.
- **Never build a shell string.** All subprocess calls use an argument list with `shell=False`. No "custom GDAL command" input exists anywhere in the product.
- **Zoom range:** integers, `0 <= min <= max <= 22`. **Resampling:** one of `nearest | bilinear | cubic | cubicspline | lanczos`, default `bilinear`. **Profile:** always `mercator`. **Scheme:** always `xyz`.
- **The source file is never modified.** Normalisation writes to `working/clean.tif`.
- **Filesystem paths key off the dataset UUID only** — never the slug, never the uploaded filename.
- **Every resolved path must satisfy `is_relative_to()` its dataset root** before use. The tile route is additionally confined to `output/tiles`.
- **Upload allowlist:** `.tif`, `.tiff`, plus TIFF magic bytes (`II*\0`, `MM\0*`, `II+\0`, `MM\0+`) **and** `gdalinfo` must open it.
- **Job state is authoritative in the database**, not in the queue.
- **Map rules (non-negotiable, from `map-dashboard-starter`):** VWorld URLs are `{z}/{y}/{x}` with `maxNativeZoom=19`; ortho/XYZ URLs are `{z}/{x}/{y}`; `MapContainer` must set `maxZoom={22}`; every miss-prone `TileLayer` sets `errorTileUrl={TRANSPARENT_TILE_DATA_URL}`.
- **Design system:** all colours come from `design-system/tokens.ts` (`C` object). No hardcoded hex in components. Outfit + Pretendard type stack. All spacing a multiple of 4px. Both themes required. Single-button theme toggle (icon = current mode).
- **Default ports:** backend `9010`, frontend dev `5173`. (9005, the starter's default, is already taken on this machine.)

### Known template defect to fix (Task 8)

The `map-dashboard-starter` backend returns `{"token": ..., "user": ...}` from `/api/auth/login`, but its frontend `services/api.ts` reads `res.access_token` and therefore never stores the token. RasterForge standardises on `{"access_token", "user"}` and updates both sides.

---

## File Structure

```
raster-forge/
├── docs/
│   ├── PRD.md                      spec
│   └── PLAN.md                     this file
├── rf-backend/
│   ├── run.py                      entrypoint (socketio.run, port 9010)
│   ├── init_db.py                  create_all + seed admin
│   ├── config.py                   env-driven config incl. GDAL + limits
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py             application factory, blueprint wiring, restart recovery
│   │   ├── models.py               User, Dataset, RasterMetadata, ProcessingJob, TileOutput
│   │   ├── storage.py              path layout + traversal-safe resolution + disk checks
│   │   ├── auth.py                 /api/auth  (login/me/logout)
│   │   ├── health.py               /api/health
│   │   ├── datasets.py             /api/datasets  upload, list, get, patch, delete, inspect
│   │   ├── jobs.py                 /api/jobs      list, get, cancel, logs; tile-job creation
│   │   ├── publish.py              /api/datasets/{id}/publish + /tiles/<slug>/<z>/<x>/<y>.png
│   │   ├── downloads.py            /api/datasets/{id}/download/*
│   │   ├── admin.py                /api/admin/stats, /api/admin/users
│   │   ├── errors.py               error codes -> human messages
│   │   └── ws.py                   SocketIO heartbeat + job:progress emitter
│   └── raster/
│       ├── gdal_runner.py          binary discovery, env injection, streaming subprocess
│       ├── inspect.py              gdalinfo -json -> RasterInfo
│       ├── analysis.py             NoData decision + zoom recommendation (pure)
│       ├── pipeline.py             normalise -> tile, progress reporting
│       ├── validate.py             tile output validation
│       ├── publisher.py            Publisher interface + LocalPublisher
│       ├── queue.py                JobQueue interface + ThreadJobQueue
│       ├── joblog.py               structured per-job log writer
│       └── cli.py                  Phase-0 harness: inspect / tile without the web app
├── rf-backend/tests/
│   ├── test_gdal_runner.py
│   ├── test_inspect.py
│   ├── test_analysis.py
│   ├── test_validate.py
│   ├── test_storage.py
│   └── test_api.py
├── rf-frontend/
│   └── src/
│       ├── main.tsx                routes + Layout
│       ├── config/config.ts        APP identity, API, VWorld, tiles
│       ├── design-system/tokens.ts unchanged from template
│       ├── components/             template shell (Topbar, MapView, tile layers, …)
│       │   └── rf/                 RasterForge components
│       │       ├── StatusPill.tsx
│       │       ├── StatTile.tsx
│       │       ├── UploadZone.tsx
│       │       ├── MetadataPanel.tsx
│       │       ├── BandTable.tsx
│       │       ├── NoDataWarning.tsx
│       │       ├── ZoomRangePicker.tsx
│       │       ├── JobProgress.tsx
│       │       ├── PipelineSteps.tsx
│       │       ├── LogViewer.tsx
│       │       ├── TileUrlBox.tsx
│       │       └── TilePreviewMap.tsx
│       ├── pages/
│       │   ├── LoginPage.tsx
│       │   ├── DashboardPage.tsx
│       │   ├── DatasetsPage.tsx
│       │   ├── DatasetDetailPage.tsx   analysis | configure | processing | completed
│       │   ├── JobsPage.tsx
│       │   └── AdminPage.tsx
│       ├── services/
│       │   ├── api.ts              generic client (template, token contract fixed)
│       │   └── rasterforge.ts      typed RasterForge endpoints
│       ├── hooks/
│       │   ├── useTheme.ts         template
│       │   ├── useBackendStatus.ts template
│       │   └── useJobPolling.ts    poll a job while active
│       └── types/rasterforge.ts    Dataset, RasterMetadata, Job, TileOutput
└── infra/
    ├── nginx/rasterforge.conf
    └── docker/{Dockerfile.backend,Dockerfile.frontend,docker-compose.yml}
```

---

# Phase 0 — Processing proof of concept

Prove the GDAL pipeline works against real orthomosaics **before** any web code. This is the spec's own Phase 0 and it de-risks everything after it.

### Task 1: GdalRunner — binary discovery and streaming execution

**Files:**
- Create: `rf-backend/raster/gdal_runner.py`
- Test: `rf-backend/tests/test_gdal_runner.py`

**Interfaces:**
- Produces:
  - `class GdalNotFound(RuntimeError)`
  - `find_gdal_tool(name: str) -> Path` — `name` in `{"gdalinfo", "gdal_translate", "gdalwarp", "gdal2tiles"}`
  - `gdal_env() -> dict[str, str]` — `os.environ` plus `GDAL_DATA`, `PROJ_LIB`
  - `class GdalRunner` with
    `run(args: list[str], on_line: Callable[[str], None] | None = None, timeout: int | None = None) -> int`
    and `run_capture(args: list[str]) -> tuple[int, str]`
  - `class GdalProcessCancelled(Exception)`
  - `runner.cancel()` terminates the live subprocess

- [ ] **Step 1: Write the failing test**

```python
# rf-backend/tests/test_gdal_runner.py
from pathlib import Path
import pytest
from raster.gdal_runner import find_gdal_tool, gdal_env, GdalRunner

def test_finds_gdalinfo():
    p = find_gdal_tool("gdalinfo")
    assert p.exists() and p.name.lower().startswith("gdalinfo")

def test_finds_gdal2tiles():
    p = find_gdal_tool("gdal2tiles")
    assert p.exists()

def test_env_defines_gdal_data():
    env = gdal_env()
    assert Path(env["GDAL_DATA"]).is_dir()

def test_runner_streams_lines_and_returns_zero():
    lines = []
    rc = GdalRunner().run([str(find_gdal_tool("gdalinfo")), "--version"], on_line=lines.append)
    assert rc == 0
    assert any("GDAL" in l for l in lines)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd rf-backend && python -m pytest tests/test_gdal_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'raster.gdal_runner'`

- [ ] **Step 3: Implement**

Discovery searches, in order: `GDAL_BIN_DIR` / `GDAL2TILES_PATH` env, then each candidate root's `bin/` and `apps/Python312/Scripts/`, then `shutil.which`. Candidate roots are globbed (`C:/Program Files/QGIS *`, `C:/OSGeo4W`) so a QGIS upgrade does not break it. `gdal_env()` resolves `GDAL_DATA` from the same root the binary came from, trying `apps/gdal/share/gdal` then `share/gdal`, and `PROJ_LIB` from `share/proj` then `apps/proj/share/proj`. Results are cached in a module-level dict.

`GdalRunner.run` uses `subprocess.Popen(args, stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8", errors="replace", env=gdal_env(), shell=False)`, reads with `read(1)` accumulating on both `\n` and `\r` (gdal2tiles writes its progress ruler with carriage returns, so line-buffered iteration would block until the phase ends), invokes `on_line` per completed segment, and honours a cancel flag by calling `proc.terminate()` then `kill()` after a grace period.

- [ ] **Step 4: Run tests and confirm they pass**

Run: `cd rf-backend && python -m pytest tests/test_gdal_runner.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add rf-backend/raster/gdal_runner.py rf-backend/tests/test_gdal_runner.py
git commit -m "feat(raster): GDAL binary discovery and streaming runner"
```

---

### Task 2: Raster inspection — `gdalinfo -json` to `RasterInfo`

**Files:**
- Create: `rf-backend/raster/inspect.py`
- Test: `rf-backend/tests/test_inspect.py`

**Interfaces:**
- Consumes: `GdalRunner.run_capture`, `find_gdal_tool` (Task 1)
- Produces:
  - `@dataclass BandInfo: index:int, dtype:str, color_interp:str, nodata:float|None, is_alpha:bool`
  - `@dataclass RasterInfo: driver:str, width:int, height:int, band_count:int, crs_name:str|None, epsg:int|None, pixel_size_x:float, pixel_size_y:float, gsd_m:float|None, bounds_wgs84:tuple[float,float,float,float]|None, center_wgs84:tuple[float,float]|None, has_alpha:bool, nodata_values:list[float|None], bands:list[BandInfo], is_geographic:bool, raw:dict`
  - `inspect_raster(path: Path) -> RasterInfo`
  - `RasterInfo.to_dict() -> dict`

- [ ] **Step 1: Write the failing test** — fixture-driven, no GDAL needed for parsing

```python
# rf-backend/tests/test_inspect.py
import json
from raster.inspect import parse_gdalinfo

RGBA_NODATA_0 = {
  "driver": "GTiff", "size": [48567, 25143],
  "coordinateSystem": {"wkt": 'PROJCRS["WGS 84 / UTM zone 52N"...]'},
  "geoTransform": [321000.0, 0.068, 0.0, 4165000.0, 0.0, -0.068],
  "wgs84Extent": {"type": "Polygon", "coordinates": [[
      [126.90,37.60],[126.94,37.60],[126.94,37.57],[126.90,37.57],[126.90,37.60]]]},
  "bands": [
    {"band":1,"type":"Byte","colorInterpretation":"Red","noDataValue":0},
    {"band":2,"type":"Byte","colorInterpretation":"Green","noDataValue":0},
    {"band":3,"type":"Byte","colorInterpretation":"Blue","noDataValue":0},
    {"band":4,"type":"Byte","colorInterpretation":"Alpha","noDataValue":0}],
  "stac": {"proj:epsg": 32652},
}

def test_parses_dimensions_and_bands():
    info = parse_gdalinfo(RGBA_NODATA_0)
    assert (info.width, info.height) == (48567, 25143)
    assert info.band_count == 4
    assert info.has_alpha is True
    assert info.bands[3].is_alpha is True

def test_parses_epsg_and_pixel_size():
    info = parse_gdalinfo(RGBA_NODATA_0)
    assert info.epsg == 32652
    assert round(info.pixel_size_x, 3) == 0.068
    assert round(info.pixel_size_y, 3) == 0.068

def test_computes_gsd_and_bounds():
    info = parse_gdalinfo(RGBA_NODATA_0)
    assert round(info.gsd_m, 3) == 0.068
    assert info.bounds_wgs84 == (126.90, 37.57, 126.94, 37.60)
    assert info.center_wgs84 is not None
```

- [ ] **Step 2: Run and confirm it fails**

Run: `cd rf-backend && python -m pytest tests/test_inspect.py -v`
Expected: FAIL — module missing

- [ ] **Step 3: Implement**

`inspect_raster` shells `gdalinfo -json <path>` via `run_capture` and hands the parsed dict to `parse_gdalinfo`, which is pure and therefore unit-testable without GDAL. EPSG is read from `stac["proj:epsg"]`, falling back to `coordinateSystem.id.code`, then a WKT `AUTHORITY["EPSG","…"]` regex. Pixel size is `abs(geoTransform[1])`, `abs(geoTransform[5])`. `is_geographic` is true when the CRS is degree-based; in that case `gsd_m = pixel_size_x * 111320 * cos(center_lat)`, otherwise `gsd_m = pixel_size_x`. Bounds come from `wgs84Extent` (min/max over the ring); when absent, `cornerCoordinates` plus a warning that bounds are in native CRS. A band is alpha when `colorInterpretation == "Alpha"`.

- [ ] **Step 4: Run tests**

Run: `cd rf-backend && python -m pytest tests/test_inspect.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(raster): parse gdalinfo -json into RasterInfo"
```

---

### Task 3: NoData decision and zoom recommendation

**Files:**
- Create: `rf-backend/raster/analysis.py`
- Test: `rf-backend/tests/test_analysis.py`

**Interfaces:**
- Consumes: `RasterInfo`, `BandInfo` (Task 2)
- Produces:
  - `NoDataMode = Literal["auto", "preserve", "remove"]`
  - `@dataclass NoDataDecision: normalise:bool, reason:str, warning:str|None`
  - `decide_nodata(info: RasterInfo, mode: NoDataMode) -> NoDataDecision`
  - `recommend_max_zoom(info: RasterInfo) -> int | None`
  - `native_zoom_for_resolution(gsd_m: float, lat: float) -> int`

- [ ] **Step 1: Write the failing test**

```python
# rf-backend/tests/test_analysis.py
from raster.analysis import decide_nodata, native_zoom_for_resolution

def test_auto_normalises_when_alpha_and_nodata_zero(rgba_nodata0):
    d = decide_nodata(rgba_nodata0, "auto")
    assert d.normalise is True
    assert "Alpha" in d.warning

def test_auto_leaves_clean_raster_alone(rgb_no_nodata):
    d = decide_nodata(rgb_no_nodata, "auto")
    assert d.normalise is False
    assert d.warning is None

def test_preserve_never_normalises(rgba_nodata0):
    assert decide_nodata(rgba_nodata0, "preserve").normalise is False

def test_remove_always_normalises(rgb_no_nodata):
    assert decide_nodata(rgb_no_nodata, "remove").normalise is True

def test_native_zoom_for_68mm_at_seoul():
    assert native_zoom_for_resolution(0.068, 37.58) == 21

def test_native_zoom_is_clamped_to_22():
    assert native_zoom_for_resolution(0.0001, 37.58) == 22
```

- [ ] **Step 2: Run and confirm it fails**

Run: `cd rf-backend && python -m pytest tests/test_analysis.py -v`

- [ ] **Step 3: Implement**

```python
EARTH_CIRCUMFERENCE_M = 156543.03392804097  # m/px at z0 on the equator

def native_zoom_for_resolution(gsd_m: float, lat: float) -> int:
    if gsd_m <= 0:
        return 22
    z = math.log2(EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat)) / gsd_m)
    return max(0, min(22, math.floor(z)))
```

`decide_nodata` for `"auto"`: normalise only when `info.has_alpha and any(nd == 0 for nd in info.nodata_values if nd is not None)`; the warning is the spec's §8.2 sentence. `"preserve"` always returns `normalise=False`, `"remove"` always `True` — but both still carry the warning when the risky condition holds, so the UI can show it regardless of the chosen mode.

- [ ] **Step 4: Run tests** — 6 passed
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(raster): NoData decision + native zoom recommendation"
```

---

### Task 4: Tile pipeline with progress reporting

**Files:**
- Create: `rf-backend/raster/pipeline.py`, `rf-backend/raster/joblog.py`

**Interfaces:**
- Consumes: Tasks 1–3
- Produces:
  - `@dataclass TileParams: min_zoom:int, max_zoom:int, resampling:str, nodata_mode:NoDataMode, processes:int`
  - `@dataclass PipelineResult: tiles_dir:Path, working_tif:Path|None, tile_count:int, size_bytes:int, min_zoom:int, max_zoom:int`
  - `ProgressFn = Callable[[int, str], None]`  (percent, current_step)
  - `run_tile_pipeline(source, dataset_dir, params, info, log, progress, should_cancel) -> PipelineResult`
  - `class JobLog` with `.info/.warn/.error(step, message)` and `.path`

- [ ] **Step 1: Write the failing test for progress parsing (pure, no GDAL)**

```python
# rf-backend/tests/test_pipeline.py
from raster.pipeline import Gdal2TilesProgress

def test_maps_base_tiles_to_first_70_percent():
    p = Gdal2TilesProgress()
    p.feed("Generating Base Tiles:")
    assert p.feed("0...10...20...30") == (21, "Generating base tiles (30%)")

def test_maps_overview_tiles_to_70_95():
    p = Gdal2TilesProgress()
    p.feed("Generating Base Tiles:")
    p.feed("0...10...100 - done.")
    p.feed("Generating Overview Tiles:")
    assert p.feed("0...10...20...30...40...50") == (82, "Generating overview tiles (50%)")

def test_ignores_unrelated_lines():
    p = Gdal2TilesProgress()
    assert p.feed("Warning 3: Cannot find tms_MapML_APSTILE.json") is None
```

- [ ] **Step 2: Run and confirm it fails**

- [ ] **Step 3: Implement**

`Gdal2TilesProgress` tracks a phase (`base` | `overview`) set by the header lines, and on each fed segment takes the **last** integer in the dotted ruler as the phase percentage. Base maps to `0–70`, overview to `70–95`. `feed` returns `(overall_percent, step_label)` or `None` when nothing changed.

`run_tile_pipeline` then:
1. `progress(2, "Validating raster")`
2. `decide_nodata`; if normalising, run `gdal_translate <src> <working/clean.tif> -a_nodata none -co TILED=YES -co COMPRESS=DEFLATE`, reporting `progress(5..15, "Normalising raster")`.
3. Run `gdal2tiles --profile=mercator -z {min}-{max} --xyz -r {resampling} --processes={n} <input> <tiles_dir>`, feeding every streamed line to both `JobLog` and `Gdal2TilesProgress`.
4. `progress(96, "Counting tiles")` — walk `tiles_dir` for `*.png`, summing count and bytes.
5. Return `PipelineResult`.

`should_cancel()` is polled between steps and inside the line callback; when true, the runner is cancelled and `GdalProcessCancelled` is raised.

`JobLog` writes `{iso8601}Z {LEVEL:5} {step:11} {message}` lines to `logs/job-{id}.log`, opening in append mode with UTF-8 (Korean dataset names appear in log lines).

- [ ] **Step 4: Run tests** — 3 passed
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(raster): tile pipeline with gdal2tiles progress parsing"
```

---

### Task 5: Output validation

**Files:**
- Create: `rf-backend/raster/validate.py`
- Test: `rf-backend/tests/test_validate.py`

**Interfaces:**
- Produces:
  - `@dataclass ValidationResult: ok:bool, errors:list[str], tile_count:int, zoom_levels:list[int]`
  - `validate_tile_output(tiles_dir: Path, min_zoom: int, max_zoom: int) -> ValidationResult`

- [ ] **Step 1: Write the failing test** — build a fake pyramid in `tmp_path`

```python
def test_accepts_complete_pyramid(tmp_path):
    for z in (14, 15):
        p = tmp_path / str(z) / "1"; p.mkdir(parents=True)
        (p / "2.png").write_bytes(PNG_1PX)
    r = validate_tile_output(tmp_path, 14, 15)
    assert r.ok and r.tile_count == 2

def test_rejects_missing_zoom_level(tmp_path):
    p = tmp_path / "14" / "1"; p.mkdir(parents=True)
    (p / "2.png").write_bytes(PNG_1PX)
    r = validate_tile_output(tmp_path, 14, 15)
    assert not r.ok and any("15" in e for e in r.errors)

def test_rejects_empty_output(tmp_path):
    r = validate_tile_output(tmp_path, 14, 14)
    assert not r.ok
```

- [ ] **Step 2: Run and confirm it fails**
- [ ] **Step 3: Implement** — check the directory exists, each `z` in range has a directory, at least one `.png` exists overall, and the first tile found starts with the PNG magic `\x89PNG\r\n\x1a\n` and is at least 8 bytes. Collect every failure into `errors` rather than short-circuiting, so the log names all problems at once.
- [ ] **Step 4: Run tests** — 3 passed
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(raster): tile output validation"
```

---

### Task 6: Phase-0 CLI harness

**Files:**
- Create: `rf-backend/raster/cli.py`

**Interfaces:**
- Consumes: Tasks 1–5
- Produces: `python -m raster.cli inspect <tif>` and `python -m raster.cli tile <tif> <outdir> --min 14 --max 21`

- [ ] **Step 1: Implement** the two subcommands with `argparse`, printing the metadata table from spec §8.1 and a live progress line for `tile`.
- [ ] **Step 2: Verify against a real orthomosaic**

Run: `cd rf-backend && python -m raster.cli inspect "<path to 메인행사장.tif>"`
Expected: CRS, EPSG, dimensions, pixel size, GSD, per-band table, NoData warning if applicable, recommended max zoom.

Run: `cd rf-backend && python -m raster.cli tile "<tif>" ../storage/_phase0 --min 14 --max 18`
Expected: progress reaches 100, `../storage/_phase0/tiles/{14..18}` populated, validation passes.

> **This is the Phase 0 gate.** Do not start Phase 1 until a real orthomosaic tiles successfully here. If no orthomosaic is available yet, generate a synthetic georeferenced GeoTIFF with `gdal_translate -of GTiff -a_srs EPSG:4326 -a_ullr …` and tile that.

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(raster): phase-0 CLI harness for inspect and tile"
```

---

# Phase 1 — Backend API

### Task 7: Storage layout and path safety

**Files:**
- Create: `rf-backend/app/storage.py`
- Test: `rf-backend/tests/test_storage.py`

**Interfaces:**
- Produces:
  - `dataset_root(dataset_id) -> Path`, `source_dir`, `working_dir`, `output_dir`, `tiles_dir`, `metadata_dir`, `logs_dir` (all `(dataset_id) -> Path`, all `mkdir(parents=True, exist_ok=True)`)
  - `safe_join(root: Path, *parts: str) -> Path` — raises `PathTraversal` unless the result `is_relative_to(root)`
  - `dir_size_bytes(p: Path) -> int`
  - `free_disk_bytes(p: Path) -> int`
  - `class PathTraversal(ValueError)`

- [ ] **Step 1: Write the failing test**

```python
def test_safe_join_allows_normal_paths(tmp_path):
    assert safe_join(tmp_path, "14", "1", "2.png") == tmp_path / "14/1/2.png"

@pytest.mark.parametrize("parts", [("..","..","etc"), ("14","..","..","secret"), ("/abs",)])
def test_safe_join_rejects_traversal(tmp_path, parts):
    with pytest.raises(PathTraversal):
        safe_join(tmp_path, *parts)
```

- [ ] **Step 2: Run and confirm it fails**
- [ ] **Step 3: Implement** — `(root / Path(*parts)).resolve()` then `is_relative_to(root.resolve())`. Reject absolute components and any part equal to `..` before joining, so a symlinked root cannot be escaped.
- [ ] **Step 4: Run tests** — 4 passed
- [ ] **Step 5: Commit**

---

### Task 8: Config, models, factory, auth contract fix

**Files:**
- Create: `rf-backend/config.py`, `rf-backend/app/models.py`, `rf-backend/app/__init__.py`, `rf-backend/app/health.py`, `rf-backend/app/errors.py`, `rf-backend/run.py`, `rf-backend/init_db.py`, `rf-backend/requirements.txt`
- Adapt from template: `rf-backend/app/auth.py`, `rf-backend/app/ws.py`

**Interfaces:**
- Produces: `create_app()`, `db`, `socketio`; models per spec §6.1; `ERROR_MESSAGES: dict[str, str]`; `classify_gdal_error(text) -> tuple[code, message]`

Config adds, on top of the template's keys: `STORAGE_ROOT`, `GDAL_BIN_DIR`, `GDAL2TILES_PATH`, `TILE_PUBLIC_BASE`, `MAX_UPLOAD_MB` (8192), `MAX_RASTER_PIXELS`, `MAX_CONCURRENT_RASTER_JOBS` (2), `MIN_FREE_DISK_GB` (10), `JOB_TIMEOUT_MINUTES` (240), `GDAL2TILES_PROCESSES`, `QUEUE_BACKEND` (`thread`).

- [ ] **Step 1:** Write models with UUID string primary keys (`default=lambda: str(uuid.uuid4())`), `to_dict()` on each omitting internals, and JSON columns via `db.JSON`.
- [ ] **Step 2:** Change `/api/auth/login` to return `{"access_token": token, "user": user.to_dict()}` (see Global Constraints — template defect). Keep DEMO_MODE, but default it **off** (`DEMO_MODE=0`) since the spec requires real authentication.
- [ ] **Step 3:** In `create_app`, after `db.create_all()`, run restart recovery: every `ProcessingJob` with status in `{queued, processing, publishing}` is set to `failed`, `error_code="gdal_failure"`, `error_message="Interrupted by a server restart. Re-run this job."`, and its dataset returned to `ready`.
- [ ] **Step 4:** `classify_gdal_error` maps log text to codes — `"does not have a spatial reference"`/`"Unable to compute a transformation"` -> `missing_crs`; `"not recognized as being in a supported file format"` -> `corrupted_raster`; `"No space left"`/`WinError 112` -> `insufficient_disk`; `"MemoryError"`/`"Cannot allocate"` -> `insufficient_memory`; else `gdal_failure`.
- [ ] **Step 5:** Verify: `cd rf-backend && python init_db.py` prints the seeded admin, then `python run.py` and `curl localhost:9010/api/health` returns `{"status":"ok"}`.
- [ ] **Step 6: Commit**

---

### Task 9: Job queue

**Files:**
- Create: `rf-backend/raster/queue.py`

**Interfaces:**
- Produces:
  - `class JobQueue(Protocol): submit(job_id: str) -> None; cancel(job_id: str) -> bool; active_count() -> int`
  - `class ThreadJobQueue(JobQueue)` — `ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RASTER_JOBS)`, a `dict[str, threading.Event]` of cancel flags, and a `dict[str, GdalRunner]` so `cancel()` can terminate a live subprocess
  - `get_queue(app) -> JobQueue`, memoised on the app object

- [ ] **Step 1:** Implement `ThreadJobQueue`. The worker function takes only `job_id` and opens its **own** app context via `with app.app_context():` — a captured `current_app` would raise `RuntimeError: Working outside of application context` inside the pool thread (documented gotcha in the starter's `backend-notes.md`). Every config value the worker needs is read inside that context, never from the request thread's proxy.
- [ ] **Step 2:** `cancel(job_id)` sets the event and, if a runner is registered, calls `runner.cancel()`.
- [ ] **Step 3:** Verify concurrency is bounded: submit 5 sleep-jobs with `MAX_CONCURRENT_RASTER_JOBS=2` and assert `active_count() <= 2`.
- [ ] **Step 4: Commit**

---

### Task 10: Datasets API — upload and inspection

**Files:**
- Create: `rf-backend/app/datasets.py`
- Test: `rf-backend/tests/test_api.py`

**Interfaces:**
- Produces routes: `GET /api/datasets`, `POST /api/datasets`, `GET|PATCH|DELETE /api/datasets/<id>`, `GET /api/datasets/<id>/metadata`, `POST /api/datasets/<id>/inspect`
- Helper: `slugify(display_name: str, dataset_id: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
def test_slugify_ascii():
    assert slugify("Main Event Site", "8c7bc1d0-...") == "main-event-site"

def test_slugify_korean_falls_back_to_id():
    assert slugify("메인행사장", "8c7bc1d0-e3f1-...") == "ds-8c7bc1d0"

def test_upload_rejects_non_tiff(client, auth):
    r = client.post("/api/datasets", data={"file": (BytesIO(b"not a tiff"), "x.tif")}, headers=auth)
    assert r.status_code == 400
    assert r.json["error_code"] == "unsupported_file"

def test_upload_requires_auth(client):
    assert client.post("/api/datasets").status_code == 401
```

- [ ] **Step 2: Run and confirm they fail**
- [ ] **Step 3: Implement.** Upload is streamed to `source/original.tif` in chunks (never `file.read()` — these are gigabytes). Validation order: extension allowlist, then the first 4 magic bytes, then `inspect_raster`. Any failure deletes the dataset directory and returns the error code. On success the dataset is created with status `ready`, `RasterMetadata` is populated, and `recommended_max_zoom` is computed. `DELETE` removes the row and `shutil.rmtree`s the dataset directory, and is permitted only for the owner or an admin.
- [ ] **Step 4: Run tests** — 4 passed
- [ ] **Step 5: Commit**

---

### Task 11: Jobs API and the tile-job entrypoint

**Files:**
- Create: `rf-backend/app/jobs.py`

**Interfaces:**
- Produces: `POST /api/datasets/<id>/tile-jobs`, `GET /api/jobs`, `GET /api/jobs/<id>`, `POST /api/jobs/<id>/cancel`, `GET /api/jobs/<id>/logs`, and `run_job(job_id: str)` — the worker entrypoint.

- [ ] **Step 1:** Validate the request body server-side: `min_zoom`/`max_zoom` are ints with `0 <= min <= max <= 22`; `resampling` is in the enum; `nodata_mode` is in `{auto, preserve, remove}`. Reject anything else with 400 — this is the security boundary that keeps GDAL arguments server-generated.
- [ ] **Step 2:** Run the disk pre-check from spec §18: estimate output bytes and refuse with `insufficient_disk` when free space is below the estimate plus `MIN_FREE_DISK_GB`.
- [ ] **Step 3:** Create the `ProcessingJob` (`queued`), set the dataset to `queued`, and `queue.submit(job.id)`.
- [ ] **Step 4:** `run_job` opens its own app context, transitions to `processing`, builds a `JobLog`, and calls `run_tile_pipeline` with a `progress` callback that writes `progress`/`current_step` to the DB (throttled to at most one write per second) and emits `job:progress` over SocketIO. On success it creates the `TileOutput`, calls `validate_tile_output`, then the publisher. On `GdalProcessCancelled` it marks `cancelled`. On any other exception it marks `failed` with a classified error code.
- [ ] **Step 5:** `GET /api/jobs/<id>/logs` returns the last N lines (default 500, `?tail=` overridable) — never the whole file.
- [ ] **Step 6: Verify** end-to-end with the Phase-0 test raster via `curl`: create a job, poll until `completed`, confirm `progress == 100`.
- [ ] **Step 7: Commit**

---

### Task 12: Publishing and tile serving

**Files:**
- Create: `rf-backend/app/publish.py`, `rf-backend/raster/publisher.py`

**Interfaces:**
- Produces:
  - `class Publisher(Protocol): publish(dataset, output) -> str` (returns the URL template)
  - `class LocalPublisher(Publisher)`
  - `POST /api/datasets/<id>/publish` — retry, idempotent
  - `GET /api/datasets/<id>/preview` — bounds, center, zoom range, URL template
  - `GET /tiles/<slug>/<int:z>/<int:x>/<path:rest>` — public, no auth

- [ ] **Step 1:** `LocalPublisher.publish` validates output, writes `metadata/metadata.json`, sets `is_published`/`published_at`, and returns `f"{TILE_PUBLIC_BASE}/{slug}/{{z}}/{{x}}/{{y}}.png"`.
- [ ] **Step 2:** The tile route resolves the slug to a dataset, then `safe_join(tiles_dir(dataset.id), str(z), str(x), rest)`, and 404s on `PathTraversal` or a missing file. It must **never** accept a dataset id, and must never resolve outside `output/tiles` — that is what keeps source GeoTIFFs unreachable. Serve with `send_file`, `Cache-Control: public, max-age=86400`.
- [ ] **Step 3: Write the failing security test**

```python
@pytest.mark.parametrize("rest", ["../../../source/original.tif", "..%2f..%2fsecret", "....//y.png"])
def test_tile_route_refuses_traversal(client, published_dataset, rest):
    r = client.get(f"/tiles/{published_dataset.slug}/14/1/{rest}")
    assert r.status_code == 404
```

- [ ] **Step 4: Run tests** and confirm all traversal attempts 404.
- [ ] **Step 5:** Verify a real tile loads: `curl -I localhost:9005/tiles/<slug>/14/…/….png` returns 200 `image/png`.
- [ ] **Step 6: Commit**

---

### Task 13: Downloads and admin

**Files:**
- Create: `rf-backend/app/downloads.py`, `rf-backend/app/admin.py`

**Interfaces:**
- Produces: the four download routes from spec §14, plus `GET /api/admin/stats` and `GET /api/admin/users`.

- [ ] **Step 1:** Source, working and metadata downloads use `send_file(..., as_attachment=True)` with a `download_name` built from the slug — never the raw uploaded filename.
- [ ] **Step 2:** The tiles ZIP is built to `output/{slug}_tiles.zip` with `zipfile.ZipFile(..., "w", ZIP_STORED, allowZip64=True)` — stored, because PNGs are already compressed and the operation is I/O-bound. Rebuild only when the zip is missing or older than the tiles directory's newest file. Run a free-disk check first and return `packaging_failed` with a clear message rather than filling the volume.
- [ ] **Step 3:** Admin routes require `role == "admin"`; return dataset/job counts, storage bytes by dataset, free disk, failed jobs, and the resolved GDAL paths (useful for diagnosing a broken install).
- [ ] **Step 4: Verify** each download returns the right content type and a non-zero length.
- [ ] **Step 5: Commit**

---

# Phase 2 — Frontend

### Task 14: Copy the starter shell and apply RasterForge config

**Files:**
- Copy: `template/frontend/*` -> `rf-frontend/`
- Modify: `rf-frontend/package.json` (name), `rf-frontend/index.html` (title, Outfit + Pretendard links), `rf-frontend/src/config/config.ts`, `rf-frontend/.env`
- Delete: `src/pages/StubPageA.tsx`, `StubPageB.tsx`, `MapDashboardPage.tsx`, `src/services/orthoApi.ts` usage for sample items

- [ ] **Step 1:** Copy the template verbatim, then `npm install`.
- [ ] **Step 2:** Set `.env`: `VITE_APP_NAME="RasterForge"`, `VITE_APP_COPYRIGHT`, `VITE_API_BASE_URL=http://localhost:9005`, `VITE_AUTH_ENABLED=true`, `VITE_DEMO_MODE=false`, `VITE_TILE_PUBLIC_BASE=http://localhost:9005/tiles`, map center Seoul.
- [ ] **Step 3:** Add `TILE_CONFIG.PUBLIC_BASE` to `config.ts`. Leave every VWorld and ortho constant untouched.
- [ ] **Step 4: Verify** `npm run build` passes `tsc` with the template's `noUnusedLocals`/`noUnusedParameters` settings.
- [ ] **Step 5: Commit**

---

### Task 15: Types, API client, job polling hook

**Files:**
- Create: `rf-frontend/src/types/rasterforge.ts`, `rf-frontend/src/services/rasterforge.ts`, `rf-frontend/src/hooks/useJobPolling.ts`
- Modify: `rf-frontend/src/services/api.ts` (token contract fix)

**Interfaces:**
- Produces: `Dataset`, `RasterMetadata`, `BandInfo`, `ProcessingJob`, `TileOutput`, `DatasetStatus`, `JobStatus`; `rf.listDatasets()`, `rf.getDataset(id)`, `rf.uploadDataset(file, name, onProgress)`, `rf.createTileJob(id, params)`, `rf.getJob(id)`, `rf.cancelJob(id)`, `rf.getJobLogs(id, tail)`, `rf.publish(id)`, `rf.getPreview(id)`, `rf.adminStats()`; `useJobPolling(jobId, { intervalMs = 1500 })`.

- [ ] **Step 1:** In `api.ts`, change `login()` to read `res.access_token` **and** store it — matching the backend fix from Task 8. Add an `upload()` helper using `XMLHttpRequest` (not `fetch`) because upload progress events are required and `fetch` cannot report them.
- [ ] **Step 2:** `useJobPolling` polls while the job status is `queued|processing|publishing`, stops on a terminal status, and clears its interval on unmount.
- [ ] **Step 3: Verify** `npm run build` passes.
- [ ] **Step 4: Commit**

---

### Task 16: Shell — routes, nav, login

**Files:**
- Modify: `rf-frontend/src/main.tsx`
- Rewrite: `rf-frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1:** Routes: `/` Dashboard, `/datasets`, `/datasets/:id`, `/jobs`, `/admin`, `/login`. Nav items with Lucide icons (`LayoutDashboard`, `Layers`, `ListChecks`, `ShieldCheck`); the Admin item renders only for `role === "admin"`.
- [ ] **Step 2:** The topbar is **not** an overlay here — RasterForge's pages are documents, not full-bleed maps — so `overlay={false}` and no glass on the topbar, per the design system's rule that glass needs real content behind it. The one exception is the dataset preview map, which is a bounded card, not a full-bleed surface.
- [ ] **Step 3: Verify** login against the real backend stores the token and `/api/auth/me` succeeds.
- [ ] **Step 4: Commit**

---

### Task 17: Shared RasterForge components

**Files:**
- Create the twelve components under `rf-frontend/src/components/rf/`

- [ ] **Step 1:** `StatusPill` maps every dataset/job status to a `STATUS` token colour plus a dot — `completed`/`ready` green, `processing`/`queued`/`publishing` amber with the pulse animation, `failed`/`cancelled` red, `uploaded`/`inspecting` neutral.
- [ ] **Step 2:** `UploadZone` follows the design system's Upload Zone recipe exactly: `1.5px dashed rgba(10,132,255,0.40)`, radius 10, `rgba(10,132,255,0.03)` background, brighter on drag-over.
- [ ] **Step 3:** `BandTable` renders band number, colour interpretation, data type and NoData, highlighting the Alpha row.
- [ ] **Step 4:** `TilePreviewMap` composes the template's `MapView` with an XYZ `TileLayer` at `maxNativeZoom={output.max_zoom}`, `maxZoom={22}`, `errorTileUrl={TRANSPARENT_TILE_DATA_URL}`, VWorld satellite beneath, and `fitBounds` on the dataset bounds.
- [ ] **Step 5: Verify** every component renders in both themes with no hardcoded hex.
- [ ] **Step 6: Commit**

---

### Task 18: Dashboard, Datasets, Upload

**Files:**
- Create: `rf-frontend/src/pages/DashboardPage.tsx`, `DatasetsPage.tsx`

- [ ] **Step 1:** Dashboard: four stat tiles (datasets, published, running jobs, storage used), an `UploadZone`, and a recent-datasets list.
- [ ] **Step 2:** Upload posts with progress, then navigates to `/datasets/{id}` on success.
- [ ] **Step 3:** Datasets page: a table with name, status pill, CRS, dimensions, GSD, zoom range, size, owner, actions.
- [ ] **Step 4: Verify** uploading a real GeoTIFF lands on the detail page showing parsed metadata.
- [ ] **Step 5: Commit**

---

### Task 19: Dataset detail — the four-state page

**Files:**
- Create: `rf-frontend/src/pages/DatasetDetailPage.tsx`

- [ ] **Step 1:** Branch on dataset status: `ready` -> analysis + configure; `queued|processing|publishing` -> progress; `completed` -> preview; `failed` -> error card with the human message and a log viewer; `publish_failed` -> "Processing completed / Publishing failed" with a **Retry publish** button that calls `POST /api/datasets/{id}/publish` and does *not* re-run tiling.
- [ ] **Step 2:** Configure section: output format (XYZ selected, others disabled and labelled "Coming later"), zoom min/max, the native recommendation line, an over-native warning when `max > recommended`, NoData select, resampling select, and a confirmation summary matching spec §9.
- [ ] **Step 3:** Processing section: progress bar, current step, elapsed timer, the seven-step pipeline checklist, a log viewer, and Cancel.
- [ ] **Step 4:** Completed section: `TilePreviewMap`, the tile URL with a Copy button, zoom range, format, published date, size, and the download buttons.
- [ ] **Step 5: Verify** the full journey: upload -> configure -> generate -> reload the page mid-job and confirm progress continues -> preview -> copy URL -> download.
- [ ] **Step 6: Commit**

---

### Task 20: Jobs and Admin pages

**Files:**
- Create: `rf-frontend/src/pages/JobsPage.tsx`, `AdminPage.tsx`

- [ ] **Step 1:** Jobs page lists all jobs with dataset name, status, progress, duration, and cancel/view-log actions.
- [ ] **Step 2:** Admin page shows users, storage by dataset, failed jobs, and the resolved GDAL paths.
- [ ] **Step 3: Verify** `npm run build` passes and both pages render in both themes.
- [ ] **Step 4: Commit**

---

# Phase 3 — Deployment integration and hardening

### Task 21: Infra and documentation

**Files:**
- Create: `infra/nginx/rasterforge.conf`, `infra/docker/Dockerfile.backend`, `Dockerfile.frontend`, `docker-compose.yml`, `README.md`, `rf-backend/.env.example`, `rf-frontend/.env.example`, `.gitignore`

- [ ] **Step 1:** The nginx config serves `/tiles/` from the storage volume with a one-day cache and proxies `/api/` to the backend, documenting both the mounted-storage and separate-host deployments.
- [ ] **Step 2:** The backend Dockerfile starts from `ghcr.io/osgeo/gdal:ubuntu-small-3.10.3` so `gdal2tiles` is present without QGIS. Note in the README that `GDAL_BIN_DIR` is unnecessary in the container because the tools are on PATH.
- [ ] **Step 3:** README covers: prerequisites, the QGIS GDAL requirement on Windows, `python init_db.py`, running both servers, and the deploy TODO list (real `SECRET_KEY`/`JWT_SECRET_KEY`, `DEMO_MODE=0`, `TILE_PUBLIC_BASE`, `CORS_ORIGINS`, VWorld key).
- [ ] **Step 4:** `.gitignore` excludes `storage/`, `*.db`, `.env`, `node_modules/`, `__pycache__/`.
- [ ] **Step 5: Commit**

---

### Task 22: Hardening pass

- [ ] **Step 1:** Confirm restart recovery works — start a job, kill the API, restart, and confirm the job reads `failed` with the interruption message rather than hanging at `processing`.
- [ ] **Step 2:** Confirm cancellation actually kills the GDAL subprocess (check Task Manager, not just the API response).
- [ ] **Step 3:** Confirm the disk pre-check rejects a job when free space is below threshold.
- [ ] **Step 4:** Re-run the traversal tests from Task 12 and add `/api/datasets/{other-users-id}` authorisation tests.
- [ ] **Step 5:** Run the full backend suite and the frontend build one final time.
- [ ] **Step 6: Commit**

---

## Verification commands

```bash
cd rf-backend && python -m pytest tests/ -v
```

```bash
cd rf-frontend && npm run build
```

```bash
cd rf-backend && python run.py
```

```bash
cd rf-frontend && npm run dev
```

---

## Self-review notes

**Spec coverage.** Every numbered section of `docs/PRD.md` maps to at least one task: §6 model -> T8; §7.1 storage -> T7; §7.2 GDAL -> T1; §7.3 queue -> T9; §8.1 -> T2; §8.2 -> T3; §8.3 -> T3; §8.4 -> T4; §9 -> T11, T19; §10 -> T12; §11 -> T12; §12 -> T17; §13 -> T5; §14 -> T13; §15 -> T8; §16 -> T10–T13; §17 -> T7, T10, T12, T22; §18 -> T11; §19 -> T4; §20 -> T16–T20; §21 acceptance -> T19 step 5 and T22.

**Type consistency.** `RasterInfo`/`BandInfo` (T2) are the only raster metadata types and are consumed unchanged by T3, T4 and T10. `TileParams`/`PipelineResult` (T4) are consumed by T11. `validate_tile_output` (T5) is called from T11 and T12 with the same signature. Frontend `Dataset`/`ProcessingJob`/`TileOutput` (T15) mirror the backend `to_dict()` shapes from T8.

**Known risk.** `gdal2tiles` progress parsing depends on its stdout format, which is not a stable contract across GDAL versions. Task 4 isolates that in `Gdal2TilesProgress` with pure unit tests, so a format change is a one-class fix; and because the pipeline's success is determined by `validate_tile_output`, not by progress reaching 100, a parsing regression degrades the progress bar without ever producing a false success.
