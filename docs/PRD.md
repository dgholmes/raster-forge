# RasterForge — Engineering PRD (MVP)

> **From GeoTIFF to deployable web maps.**

**Status:** MVP, implementation-ready
**Date:** 2026-09-01
**Supersedes:** the original product PRD. This document keeps that document's scope and intent, but resolves every open decision against the *actual* target environment (verified below) so it can be built from directly.

---

## 1. What this is

RasterForge converts geospatial raster datasets — initially GeoTIFF orthomosaics — into web-ready XYZ map tiles and publishes them at a stable URL, without an operator ever opening OSGeo4W Shell, typing a GDAL command, or running SCP.

The single MVP workflow:

```
Upload GeoTIFF → Inspect → Configure → Process → Validate → Publish → Preview → Copy URL / Download
```

Everything outside that line is post-MVP.

---

## 2. The problem, concretely

Publishing one orthomosaic today means: find the `.tif`, open OSGeo4W Shell, reason about NoData, maybe run `gdal_translate`, run `gdal2tiles`, pick zoom levels, wait, eyeball the generated OpenLayers preview, SCP the output to the tile host, work out the final URL, then wire that URL into another app.

```bash
gdal2tiles --profile=mercator -z 14-22 --xyz input.tif output_tiles
```

```bash
gdal_translate input.tif clean.tif -a_nodata none -co TILED=YES -co COMPRESS=DEFLATE
```

That process requires GDAL knowledge, produces inconsistent commands, has no job tracking, no central asset registry, and a manual file-transfer step that is easy to get wrong.

---

## 3. Verified target environment

These were checked on the development machine before this document was written. They are load-bearing: the design depends on them.

| Component | Status | Location |
|---|---|---|
| `gdalinfo` (with `-json`) | OK — GDAL 3.10.3 | `C:\Program Files\QGIS 3.42.2\bin\gdalinfo.exe` |
| `gdal_translate` | OK | `C:\Program Files\QGIS 3.42.2\bin\gdal_translate.exe` |
| `gdalwarp` | OK | `C:\Program Files\QGIS 3.42.2\bin\gdalwarp.exe` |
| `gdal2tiles.exe` | OK | `C:\Program Files\QGIS 3.42.2\apps\Python312\Scripts\gdal2tiles.exe` |
| `GDAL_DATA` | must be injected | `...\QGIS 3.42.2\apps\gdal\share\gdal` |
| `PROJ_LIB` | must be injected | `...\QGIS 3.42.2\share\proj` |
| OSGeo4W (GDAL 3.11.0) | present, but **no `gdal2tiles`** | `C:\OSGeo4W\bin` |
| Python | OK — 3.11.9 | on PATH |
| Node / npm | OK — 22.16.0 / 11.5.2 | on PATH |
| Redis | **not installed** | — |
| Docker | OK — 29.2.0 | for production packaging |

**Consequences:**

1. **QGIS is the GDAL source of truth**, because it is the only install carrying `gdal2tiles`. OSGeo4W lacks it entirely.
2. **`GDAL_DATA` must be injected** into every subprocess. Running `gdal2tiles.exe` without it emits `Warning 3: Cannot find tms_MapML_APSTILE.json (GDAL_DATA is not defined)`.
3. **No Redis**, so the queue cannot be RQ/Celery-only if the MVP is to run on this machine today. See §7.3.

---

## 4. Resolved decisions (deviations from the original PRD)

Each of these departs from a *recommendation* in the source PRD. The recommendation, the decision, and the reason are recorded so they can be revisited deliberately.

### 4.1 Leaflet, not OpenLayers, for the map preview

- **Original:** "Recommended map library: OpenLayers."
- **Decision:** Leaflet + react-leaflet.
- **Why:** the lab's `map-dashboard-starter` ships a debugged Leaflet tile stack whose rules are marked non-regressable — VWorld `{z}/{y}/{x}` ordering, `maxNativeZoom=19` (z20+ returns an XML error at HTTP 200), the z19 to z22 overscale trick, transparent `errorTileUrl` on every miss-prone layer, and the closed-network proxy. Rebuilding that on OpenLayers re-opens bugs that are already closed. An XYZ pyramid renders identically in either library, so the preview loses nothing, and RasterForge gains a VWorld satellite basemap under the orthomosaic for free.
- **Cost:** if a consumer later needs an OpenLayers preview snippet, that is a documentation change, not an architecture change.

### 4.2 Pluggable job queue; threaded worker is the default

- **Original:** "Redis + Celery, or Redis + RQ."
- **Decision:** a `JobQueue` interface with two implementations — `ThreadJobQueue` (default, in-process, bounded pool) and `RQJobQueue` (opt-in via `QUEUE_BACKEND=rq`).
- **Why:** Redis is not installed and has no first-class Windows build. A threaded queue satisfies every MVP requirement that matters — jobs survive the browser closing, concurrency is bounded by `MAX_CONCURRENT_RASTER_JOBS`, status is durable, jobs are cancellable — because the *database*, not the queue, is the source of truth for job state. Swapping in Redis later is a config change.
- **Cost:** in-process jobs do not survive an API restart. Handled explicitly: on boot, any job still marked `processing` is failed with an "interrupted by server restart" message and is re-runnable.

### 4.3 SQLite by default, PostgreSQL supported

- **Original:** "PostgreSQL. PostGIS recommended."
- **Decision:** `DATABASE_URL` drives it; SQLite is the default.
- **Why:** zero setup on the dev box. Every model is plain SQLAlchemy, so pointing at Postgres is a one-line env change. Raster bounds are stored as explicit `min_lon/min_lat/max_lon/max_lat` floats *plus* a JSON blob, so a PostGIS geometry column can be added later without reshaping the schema.

### 4.4 Tiles are served from where they are generated

- **Original:** "Preferred architecture — generate directly into persistent storage already mounted by the tile server", with SCP/rsync as the fallback.
- **Decision:** the worker writes the pyramid to `storage/datasets/{id}/output/tiles/`. Publishing does **not** copy it. Publishing validates the output, then registers the dataset's slug; the tile route resolves `slug -> dataset` and serves from that dataset's tiles directory, and only from there.
- **Why:** this is the original PRD's own preferred architecture taken literally. It removes SCP entirely, makes publishing an O(1) metadata operation instead of an 8 GB copy, and makes publish-retry (§13) trivial. Source GeoTIFFs are never reachable through the tile route.

---

## 5. Users and roles

| Role | Can |
|---|---|
| **admin** | everything below, plus see and delete *all* datasets, manage users, view system logs and storage usage |
| **user** | upload, configure, process, preview, download, copy URLs, delete their own datasets |

Auth is username/email plus password, JWT bearer token, admin-created accounts. No SSO, no OAuth, no org-level permissions in MVP.

---

## 6. Domain model

The most important architectural rule, carried over from the source PRD:

```
Dataset  !=  ProcessingJob  !=  TileOutput  !=  Published asset
```

One uploaded raster may produce many outputs over time (XYZ 14–21, XYZ 14–22, later a COG, later PMTiles). The schema must never assume `1 GeoTIFF = 1 tile folder`.

### 6.1 Tables

**User** — `id, username, email, password_hash, role, is_active, created_at`

**Dataset** — the uploaded raster.
`id (uuid), owner_id, display_name, slug, source_filename, source_path, source_size, status, created_at, updated_at`

**RasterMetadata** — one row per dataset, the parsed `gdalinfo -json`.
`dataset_id, driver, width, height, band_count, crs_name, epsg, pixel_size_x, pixel_size_y, gsd_m, min_lon, min_lat, max_lon, max_lat, center_lon, center_lat, has_alpha, nodata_values (json), bands (json), recommended_max_zoom, metadata_json`

**ProcessingJob** — one run of a pipeline.
`id (uuid), dataset_id, type, status, progress, current_step, params (json), started_at, finished_at, error_code, error_message, log_path, created_at`

**TileOutput** — one produced artifact.
`id (uuid), dataset_id, job_id, min_zoom, max_zoom, scheme, profile, resampling, tile_count, output_path, public_url_template, size_bytes, bounds (json), published_at, is_published`

### 6.2 Dataset status

`uploaded -> inspecting -> ready -> queued -> processing -> publishing -> completed`, with `failed` and `cancelled` as terminal branches from any active state.

`completed` means tiles exist **and** are published. A dataset whose tiles generated but whose publish step failed sits at `publish_failed` — surfaced as "Processing completed / Publishing failed" — and the publish step alone is retryable. Expensive raster work is never repeated to fix a cheap publishing problem.

### 6.3 Naming: display name, slug, id

Three separate identifiers, because the uploaded filename is safe as none of them:

- **Display name** — free text, Korean welcome: `메인행사장`
- **Internal id** — UUID4; the only thing the filesystem uses
- **Slug** — URL-safe, user-editable, unique: `main-event-site`

The slug is auto-derived by ASCII-slugifying the display name. Korean, spaces, and special characters yield an empty result, so the fallback is `ds-{first 8 of uuid}`. The user may override it. The filesystem layout keys off the **id**, never the slug and never the filename, so renaming a dataset never moves a byte on disk.

---

## 7. Architecture

```
Frontend — Vite + React + TypeScript + Leaflet
    |  REST + SocketIO
Backend API — Flask
    |  auth · datasets · jobs · downloads · tiles
    |  enqueue
JobQueue (thread | rq), bounded by MAX_CONCURRENT_RASTER_JOBS
    |
Raster worker — gdalinfo · gdal_translate · gdal2tiles
    |
Persistent storage — source · working · tiles · metadata · logs
    |
Tile serving — Flask /tiles (dev), Nginx (prod)
```

### 7.1 Storage layout

```
storage/
└── datasets/
    └── {dataset-uuid}/
        ├── source/     original.tif          (never modified)
        ├── working/    clean.tif             (only if NoData normalisation ran)
        ├── output/
        │   ├── tiles/  {z}/{x}/{y}.png
        │   └── {slug}_tiles.zip              (built on demand, cached)
        ├── metadata/   metadata.json
        └── logs/       job-{job-uuid}.log
```

Every path is derived by joining the storage root with the dataset UUID and a fixed subdirectory name. No user-supplied string ever reaches a path segment.

### 7.2 GDAL invocation

A single `GdalRunner` owns all subprocess execution:

- **Discovery order** per binary: explicit env (`GDAL_BIN_DIR`, `GDAL2TILES_PATH`) -> QGIS install -> OSGeo4W -> PATH.
- **Environment injection:** `GDAL_DATA` and `PROJ_LIB` set on every subprocess, resolved from the same install the binary came from.
- **Arguments are always a list**, never a shell string, `shell=False`. No code path interpolates user input into a command.
- **Output is streamed**, appended to the job log line by line, and scanned for progress markers.

### 7.3 Queue and concurrency

`MAX_CONCURRENT_RASTER_JOBS` (default `2`) bounds the worker pool. Tile generation is CPU-, memory-, disk- and I/O-heavy; two large orthomosaics at once can exhaust the machine.

Job state lives in the database, not in the queue. The queue decides only *when* work runs. That is what makes the backend swappable, and what makes "close the browser, come back later" work by construction.

---

## 8. Pipeline

```
Uploaded GeoTIFF
      |  validate: extension, magic bytes, gdalinfo opens it
Metadata inspection            gdalinfo -json
      |
NoData decision                auto | preserve | remove
      |  (conditional)
Raster normalisation           gdal_translate -a_nodata none
      |
Tile generation                gdal2tiles --profile=mercator --xyz
      |
Output validation              §13
      |
Publish                        register slug, expose URL
      |
Preview metadata               bounds, center, zoom range
      |
Completed
```

### 8.1 Metadata inspection

`gdalinfo -json input.tif` is parsed into `RasterMetadata`. Parsing structured JSON rather than scraping human-readable text is deliberate — the text format is not a stable contract.

Extracted and displayed:

- **File** — filename, size, width x height, driver
- **Spatial** — CRS name, EPSG, extent, corner coordinates, center, pixel size, estimated GSD
- **Bands** — per band: number, data type, colour interpretation, NoData value, and whether it is the Alpha band

```
CRS          WGS 84 / UTM Zone 52N
EPSG         32652
Dimensions   48,567 x 25,143 px
Pixel Size   0.068 x 0.068 m
Approx. GSD  6.8 cm/pixel

Band 1  Red    Byte  NoData: 0
Band 2  Green  Byte  NoData: 0
Band 3  Blue   Byte  NoData: 0
Band 4  Alpha  Byte  NoData: 0
```

### 8.2 NoData analysis — the known failure

The specific condition that breaks orthomosaics today:

```
RGB + Alpha band present  AND  NoData = 0
```

When both hold, valid zero-valued pixels get treated as NoData during tiling and punch holes in the output. RasterForge detects this and warns:

> This image contains an Alpha band and also defines 0 as NoData. Valid zero-value pixels may be interpreted as transparent during processing.

**NoData handling options:**

| Option | Behaviour |
|---|---|
| **Auto** *(default)* | Normalise only when the risky condition above holds |
| **Preserve source NoData** | Tile the source as supplied |
| **Remove NoData metadata** | Always produce a normalised working copy |

Normalisation writes a *working copy*; the source is never touched:

```bash
gdal_translate input.tif clean.tif -a_nodata none -co TILED=YES -co COMPRESS=DEFLATE
```

### 8.3 Zoom recommendation

The recommended maximum zoom is the Web Mercator zoom whose ground resolution first matches the raster's native resolution:

```
res(z, lat) = 156543.03392804097 * cos(lat) / 2^z
z_native    = round( log2( 156543.03392804097 * cos(lat) / pixel_size_m ) )
```

Rounding is to *nearest*, deliberately. Truncating would stop a 6.8 cm orthomosaic at z20, whose 0.118 m/px is 1.74x coarser than the source, discarding real detail; rounding up would push a 30 m raster to z13 and upscale it 2x. Nearest yields 21 and 12 respectively.

Pixel size is converted to metres first when the CRS is geographic. At about 6.8 cm/pixel this yields **21**, and the UI says so:

> Native resolution ~6.8 cm/pixel -> recommended maximum zoom **21**. Zoom 22 will upscale the source imagery.

The user may still choose 22. It is a recommendation, not a constraint.

### 8.4 Tile generation

```bash
gdal2tiles --profile=mercator -z {min}-{max} --xyz -r {resampling} --processes={N} input.tif output/tiles
```

Fixed for MVP: profile `mercator`, scheme `xyz`. User-selectable: min zoom, max zoom, resampling (`nearest | bilinear | cubic | cubicspline | lanczos`, default **bilinear**, the right default for orthophotos).

Progress is parsed from gdal2tiles' own output, which prints a phase header followed by a dotted percentage ruler:

```
Generating Base Tiles:
0...10...20...30...40...50...60...70...80...90...100 - done.
Generating Overview Tiles:
0...10...20...
```

The runner maps base-tile progress to 0–70% and overview progress to 70–95% of the job, reserving the last 5% for validation and publishing.

---

## 9. Job UI and lifecycle

The browser is never responsible for keeping GDAL alive. A user may start a job, close the tab, and return to a running or finished job.

```
Generating XYZ Tiles

Dataset      메인행사장
Status       Processing
Progress     ################----  78%
Current      Generating Zoom Level 21
Elapsed      00:08:42

[x] Upload complete
[x] Metadata inspected
[x] Raster normalised
[>] Generating tiles
[ ] Validating output
[ ] Publishing
[ ] Complete
```

Progress reaches the UI two ways: polling `GET /api/jobs/{id}` is the reliable baseline (correct across reloads and reconnects), and SocketIO `job:progress` events push updates live. Polling is authoritative; the socket is an enhancement.

Queued and processing jobs are cancellable. Cancelling terminates the GDAL subprocess, marks the job `cancelled`, and leaves partial output in place for inspection.

---

## 10. Tile output and URLs

Standard XYZ pyramid:

```
tiles/
├── 14/{x}/{y}.png
├── 15/...
└── 22/...
```

Canonical URL template:

```
{TILE_PUBLIC_BASE}/{slug}/{z}/{x}/{y}.png
```

which in development resolves to:

```
http://localhost:9005/tiles/main-event-site/{z}/{x}/{y}.png
```

and in production to whatever `TILE_PUBLIC_BASE` names, for example `https://tiles.example.com/rasterforge`. The stored `public_url_template` is exactly what **Copy URL** yields, so it pastes directly into OpenLayers, MapLibre, Leaflet, Cesium, or Unreal.

---

## 11. Publishing

Publishing is deliberately cheap and idempotent:

1. Validate the tile output (§13).
2. Ensure the slug is unique and resolvable.
3. Write `metadata/metadata.json` (bounds, center, zoom range, URL template).
4. Mark `TileOutput.is_published = true`, stamp `published_at`.
5. Set dataset status `completed`.

No file transfer. No SCP. The tile route serves from the dataset's `output/tiles` directory and refuses any path that escapes it.

For a deployment where processing and hosting genuinely sit on different hosts, `infra/nginx/` documents serving the same layout directly, and the publisher interface has a single method, so a future `RsyncPublisher` slots in without touching the pipeline.

---

## 12. Map preview

On completion the dataset page shows an interactive Leaflet map that:

- loads the generated XYZ endpoint as the top layer (`maxNativeZoom` = the output's max zoom, `maxZoom` 22, transparent `errorTileUrl`),
- renders a basemap underneath for context — VWorld satellite when a key is configured, OpenStreetMap otherwise, so there is always geographic context without requiring a key. Both stop at native zoom 19 and are overscaled to 22. OSM's licence requires visible attribution, so Leaflet's attribution control is enabled whenever a basemap is active,
- fits to the raster's bounds on load,
- supports pan and zoom to 22,
- shows live cursor coordinates and the current zoom.

This is the same map stack the rest of the lab's dashboards use, with the generated tiles substituted for the usual orthomosaic layer.

---

## 13. Output validation

Before a job may report success:

- [ ] tile root directory exists
- [ ] every requested zoom level directory exists
- [ ] tile count > 0
- [ ] at least one tile is a readable image with plausible dimensions
- [ ] bounds are finite, within Web Mercator limits, and non-degenerate
- [ ] `metadata.json` was written
- [ ] the resolved tile URL returns a tile

A failure here marks the job `failed` with a validation error code. A broken pyramid is never reported as `completed`.

---

## 14. Downloads

| Artifact | Route | Notes |
|---|---|---|
| Original GeoTIFF | `/api/datasets/{id}/download/source` | streamed |
| Generated tiles | `/api/datasets/{id}/download/tiles` | ZIP, `ZIP_STORED`, ZIP64, cached at `output/{slug}_tiles.zip` |
| Cleaned GeoTIFF | `/api/datasets/{id}/download/working` | only when normalisation ran; Advanced |
| Metadata | `/api/datasets/{id}/download/metadata` | `metadata.json` |

Tiles are already PNG-compressed, so the ZIP is stored, not deflated — the operation is I/O-bound, not CPU-bound. The archive is built once and reused until the tile output changes. A free-disk check runs first, and the request is refused with a clear message rather than filling the volume.

---

## 15. Errors

GDAL's raw output is never the user-facing message. Each failure is classified to a code with a human explanation, and the technical log stays one click away under **View Technical Log**.

```
Tile generation failed.

GDAL could not determine the source coordinate system.
Check that your GeoTIFF contains valid projection metadata.

[ View Technical Log ]
```

**Error codes:** `unsupported_file`, `corrupted_raster`, `missing_crs`, `invalid_bounds`, `invalid_nodata`, `insufficient_disk`, `insufficient_memory`, `gdal_failure`, `cancelled`, `validation_failed`, `publish_failed`, `permission_denied`, `transfer_failed`, `packaging_failed`.

---

## 16. API

```
POST   /api/auth/login              POST   /api/auth/logout
GET    /api/auth/me

GET    /api/datasets                POST   /api/datasets              (upload)
GET    /api/datasets/{id}           DELETE /api/datasets/{id}
PATCH  /api/datasets/{id}                                             (rename, slug)
GET    /api/datasets/{id}/metadata
POST   /api/datasets/{id}/inspect                                     (re-run inspection)
POST   /api/datasets/{id}/tile-jobs                                   (start processing)
GET    /api/datasets/{id}/outputs
GET    /api/datasets/{id}/preview
POST   /api/datasets/{id}/publish                                     (retry publish)

GET    /api/jobs                    GET    /api/jobs/{id}
POST   /api/jobs/{id}/cancel        GET    /api/jobs/{id}/logs

GET    /api/datasets/{id}/download/source
GET    /api/datasets/{id}/download/tiles
GET    /api/datasets/{id}/download/working
GET    /api/datasets/{id}/download/metadata

GET    /api/admin/stats                                               (admin)
GET    /api/admin/users                                               (admin)

GET    /tiles/{slug}/{z}/{x}/{y}.png                                  (public)
GET    /api/health
```

---

## 17. Security

| Requirement | Implementation |
|---|---|
| Auth required for upload/processing | `@jwt_required()` on every mutating route |
| Validate extension | allowlist `.tif`, `.tiff` |
| Don't trust the filename | TIFF magic bytes (`II*\0`, `MM\0*`, BigTIFF `II+\0`, `MM\0+`) **and** `gdalinfo` must open it |
| Sanitise filenames | stored under a UUID path; the original name is kept as metadata only |
| Never execute user shell input | `subprocess` with an argument list, `shell=False`; no custom-command field exists anywhere in the product |
| Server-side GDAL args | zooms are range-checked ints, resampling from a fixed enum, profile and scheme constant |
| Isolate processing dirs | one UUID directory per dataset |
| Prevent path traversal | every resolved path must be `is_relative_to()` its dataset root; the tile route is additionally confined to `output/tiles` |
| Limit upload size | `MAX_UPLOAD_MB` (default 8192) |
| Restrict source access | source is reachable only via the authenticated download route, never via `/tiles` |
| Log admin actions | audit line for delete, user management, publish |

The original PRD is explicit that a "Custom GDAL command" input must never exist. It does not.

---

## 18. Resource protection

Before a job is accepted:

```
check available disk  ->  estimate output size  ->  accept or reject
```

The estimate derives from source pixel count and the requested zoom span. Configurable limits: `MAX_UPLOAD_MB`, `MAX_RASTER_PIXELS`, `MAX_CONCURRENT_RASTER_JOBS`, `MIN_FREE_DISK_GB`, `JOB_TIMEOUT_MINUTES`.

---

## 19. Logging

Every job writes `storage/datasets/{id}/logs/job-{job_id}.log`, each line carrying timestamp, level, step, and message:

```
2026-09-01T11:42:03Z INFO  upload      Accepted 메인행사장.tif (4.21 GB)
2026-09-01T11:42:05Z INFO  inspect     Detected EPSG:32652, 48567x25143, 4 bands
2026-09-01T11:42:05Z WARN  nodata      Alpha band present and NoData=0 — normalising
2026-09-01T11:42:05Z INFO  pipeline    Selected: normalise -> tile
2026-09-01T11:44:51Z INFO  translate   gdal_translate completed in 166s
2026-09-01T11:53:33Z INFO  tiles       gdal2tiles completed, 184203 tiles
2026-09-01T11:53:36Z INFO  validate    All zoom levels 14–21 present
2026-09-01T11:53:36Z INFO  publish     http://localhost:9005/tiles/main-event-site/{z}/{x}/{y}.png
```

---

## 20. Screens

Navigation: **Dashboard · Datasets · Jobs · Admin**

1. **Login** — username and password.
2. **Dashboard** — storage/job/dataset stat tiles, recent datasets, prominent *Upload GeoTIFF*.
3. **Upload** — drag-and-drop `.tif`/`.tiff`, progress, size, cancel.
4. **Dataset analysis** — parsed metadata, band table, NoData warning.
5. **Configure** — output format (XYZ; others shown disabled as "Coming later"), zoom min/max with native recommendation, NoData handling, resampling, advanced section, job summary.
6. **Processing** — progress bar, current step, elapsed, pipeline checklist, log viewer, cancel.
7. **Completed** — Leaflet preview, tile URL and Copy, zoom range, format, published date, size, download actions.
8. **Jobs** — all jobs with status, dataset, duration, actions.
9. **Admin** — users, storage usage, failed jobs, system info.

The dataset detail page is one route whose body follows dataset status: analysis -> configure -> processing -> completed.

---

## 21. Acceptance criteria

The MVP is done when an operator can, entirely in a browser:

1. Log in.
2. Upload a valid GeoTIFF.
3. See it inspected automatically.
4. Read CRS, dimensions, bands, pixel size, and NoData.
5. Choose min and max zoom, with a native-resolution recommendation shown.
6. Accept automatic NoData handling or override it.
7. Start tile generation.
8. Close the page without stopping processing.
9. Return and see accurate progress.
10. Get a valid XYZ pyramid.
11. Have it published automatically on success.
12. Preview those exact tiles on an interactive map.
13. Copy the XYZ URL.
14. Use that URL in another application.
15. Download the tiles.
16. Download the original GeoTIFF.
17. Read the processing log when something fails.

With **no** OSGeo4W, no typed GDAL command, no folder copying, no SCP, no server login.

---

## 22. Explicitly out of scope for MVP

Full raster editing · DEM processing · Cesium terrain · vector tiles · MBTiles · PMTiles · COG creation · a reprojection UI beyond what `gdal2tiles` needs internally · photogrammetry · orthomosaic generation from drone photos · WebODM integration · image stitching · colour correction · multi-tenant workspaces · billing · public SaaS · distributed compute · Kubernetes · pipeline builders · raster analysis.

---

## 23. Post-MVP roadmap

| Version | Adds |
|---|---|
| 1.1 | Batch processing — many GeoTIFFs, bulk config, bulk URL export |
| 1.2 | Cloud Optimized GeoTIFF — overviews, compression, range serving |
| 1.3 | Reprojection workflows via `gdalwarp` |
| 1.4 | MBTiles (offline / mobile) |
| 1.5 | PMTiles (object storage / CDN) |
| 1.6 | Orthophoto processing — NoData repair, alpha generation, crop-to-valid, mosaicing, footprints |
| 2.0 | Cesium terrain / quantized mesh from DEM/DSM/DTM |
| 2.x | Reusable processing recipes (presets) |
| API | `POST /api/v1/jobs` for programmatic submission (WebODM -> RasterForge -> app) |

The architecture is built around a four-part abstraction so these land as new pipelines rather than redesigns:

```
INPUT  ->  PIPELINE  ->  OUTPUT  ->  PUBLISHER
```

MVP instantiates exactly one path through it: `GeoTIFF -> Web Raster Tiles -> XYZ -> Internal Tile Server`.

---

## 24. Success metric

> An operator with a finished GeoTIFF orthomosaic can publish it as working XYZ tiles to the production tile server without OSGeo4W, GDAL commands, SCP, or SSH — and the whole run is reproducible, logged, and visible in the web interface.
