# RasterForge

**From GeoTIFF to deployable web maps.**

Upload an orthomosaic, get published XYZ tiles at a copyable URL — no OSGeo4W
shell, no typed GDAL commands, no SCP.

```
Upload → Inspect → Configure → Process → Validate → Publish → Preview → Copy URL
```

- [Engineering PRD](docs/PRD.md) — what this is and why it is built this way
- [Implementation plan](docs/PLAN.md) — the task-by-task build

---

## Requirements

| | |
|---|---|
| Python | 3.11+ |
| Node | 20+ (built and tested on 22) |
| GDAL | 3.10+ **including `gdal2tiles`** |

### The GDAL requirement, precisely

`gdal2tiles` is the one hard dependency, and on Windows it is easy to get
wrong:

- **QGIS ships it. OSGeo4W does not.** OSGeo4W has `gdalinfo` and
  `gdal_translate` but no `osgeo_utils` package, so an OSGeo4W-only machine can
  inspect a raster and never tile one.
- **`gdal2tiles.exe` crashes** when launched directly — the Python entry-point
  wrapper dies with an access violation (`0xC0000005`). RasterForge therefore
  invokes it as `…\apps\Python312\python.exe -m osgeo_utils.gdal2tiles`.
- **The inherited `PATH` must be discarded.** QGIS's own `o4w_env.bat` rebuilds
  `PATH` from scratch before running anything; inheriting the ambient `PATH`
  lets a foreign GDAL/PROJ DLL load first and the process dies. RasterForge
  replicates that clean environment, plus `PYTHONHOME`, `GDAL_DATA`,
  `GDAL_DRIVER_PATH` and `PROJ_DATA`.

All of this is automatic — install QGIS and it is found. To check what the
server actually resolved:

```bash
cd rf-backend && .venv/Scripts/python -m raster.cli doctor
```

The same information appears on the **Admin** page at runtime.

---

## Quick start

### 1. Backend

```bash
cd rf-backend && python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
```

```bash
cd rf-backend && .venv/Scripts/python init_db.py
```

```bash
cd rf-backend && .venv/Scripts/python run.py
```

The API listens on **9010** and serves published tiles at
`http://localhost:9010/tiles/{slug}/{z}/{x}/{y}.png`.

> Port 9010, not the more usual 9005 — another lab service already owns 9005 on
> the development machine. Override with `PORT` in `rf-backend/.env`.

### 2. Frontend

```bash
cd rf-frontend && npm install && npm run dev
```

Open http://localhost:5173 and sign in with `admin` / `admin`.

### 3. Optional — a VWorld key

The preview always has a basemap: **OpenStreetMap** is the keyless default, so
your tiles land in real geographic context out of the box. Adding a VWorld key
swaps in Korean satellite imagery, which is usually the better backdrop for an
orthomosaic — register at https://www.vworld.kr/ and set
`VITE_VWORLD_API_KEY` in `rf-frontend/.env`, then restart the dev server
(Vite inlines `VITE_*` at startup, so a browser reload will not pick it up).

The chip in the map's top-right cycles through whatever is available —
Satellite (if keyed) → Street → off.

Two caveats:

- **Both basemaps need the internet.** On a closed network, set
  `VITE_USE_PROXY=true` and `VITE_PROXY_BASE_URL` and they route through the
  corporate proxy; with no route at all, basemap tiles fail to a transparent
  PNG and you see your ortho on the page background — the same as having no
  basemap, never a wall of broken tiles.
- **OSM's tile policy is for light use.** A preview map is well within it, but
  if RasterForge ever serves basemap tiles at volume, point it at your own
  tile server or a commercial provider.

---

## Processing without the web app

The pipeline runs standalone, which is how it was proven before any UI existed:

```bash
cd rf-backend && .venv/Scripts/python -m raster.cli inspect path/to/ortho.tif
```

```bash
cd rf-backend && .venv/Scripts/python -m raster.cli tile path/to/ortho.tif ./out --min 14 --max 21
```

`inspect` prints CRS, dimensions, pixel size, GSD, the band table, any NoData
warning, and the recommended maximum zoom. `tile` runs the full
normalise → tile → validate pipeline with live progress.

---

## Tests

```bash
cd rf-backend && .venv/Scripts/python -m pytest tests/ -q
```

101 tests. The suite includes a real upload → tile → publish → serve round trip
against GDAL, path-traversal tests against the public tile route, and a
regression test for the `gdal2tiles.exe` crash.

```bash
cd rf-frontend && npm run build
```

---

## How it fits together

```
Frontend (Vite · React · TypeScript · Leaflet)
    │  REST + SocketIO
Backend API (Flask)
    │  enqueue
JobQueue — bounded by MAX_CONCURRENT_RASTER_JOBS
    │
Raster worker — gdalinfo · gdal_translate · gdal2tiles
    │
Storage — source · working · tiles · metadata · logs
    │
Tile serving — Flask (dev) · Nginx (prod)
```

Four ideas carry most of the weight:

1. **Job state lives in the database, not the queue.** The queue only decides
   *when* work runs. That is what makes "close the browser, come back later"
   work by construction, and what lets the thread pool be swapped for Redis/RQ
   with a config change.

2. **Publishing copies nothing.** The worker generates the pyramid into
   persistent storage that the tile server already reads; publishing validates
   the output and registers the slug. So publishing is O(1) rather than an 8 GB
   move, and a publish failure is retryable without re-running the expensive
   raster work.

3. **`Dataset ≠ ProcessingJob ≠ TileOutput ≠ published asset.`** One raster can
   produce many outputs over its life. Nothing assumes `1 GeoTIFF = 1 tile
   folder`, which is what keeps COG/MBTiles/PMTiles from needing a schema
   rewrite.

4. **GDAL arguments are always server-generated.** Zooms are range-checked
   integers, resampling comes from a fixed enum, and every subprocess is an
   argument list with `shell=False`. There is no "custom GDAL command" field
   anywhere in the product, by design.

### Storage layout

```
storage/datasets/{dataset-uuid}/
├── source/     original.tif        (never modified)
├── working/    clean.tif           (only when NoData normalisation ran)
├── output/
│   ├── tiles/  {z}/{x}/{y}.png
│   └── {slug}_tiles.zip
├── metadata/   metadata.json
└── logs/       job-{job-uuid}.log
```

Paths key off the dataset **UUID** — never the slug, never the uploaded
filename. Renaming a dataset moves nothing on disk, and Korean filenames,
spaces and duplicates are all non-issues.

---

## Deployment

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

The backend image is based on `ghcr.io/osgeo/gdal`, which includes
`gdal2tiles` on `PATH` — none of the Windows discovery machinery applies
inside the container.

`infra/nginx/rasterforge.conf.template` documents both serving shapes: reading
tiles directly from the shared storage volume (preferred), or proxying
`/tiles/` to the API. The API address is the `RF_API_UPSTREAM` variable. The
frontend image renders it at start-up, defaulting to `api:9010`, the Compose
service name. On a bare-metal host render it once with `envsubst`, as the
file's header shows.

### Before going live

- [ ] Set real `SECRET_KEY` and `JWT_SECRET_KEY`
- [ ] Change `ADMIN_PASSWORD`, and confirm `DEMO_MODE=0`
- [ ] Set `TILE_PUBLIC_BASE` to the public tile host — it is what **Copy URL**
      hands the user, so `localhost` will not do
- [ ] Set `CORS_ORIGINS` to the frontend origin, not `*`
- [ ] Point `STORAGE_ROOT` at a volume with room for the pyramids
- [ ] Review `MAX_UPLOAD_MB`, `MIN_FREE_DISK_GB`, `MAX_CONCURRENT_RASTER_JOBS`
- [ ] Add `VITE_VWORLD_API_KEY` if you want the satellite basemap

---

## Known limits

- **In-process jobs do not survive an API restart.** This is handled rather
  than hidden: on boot, any job still marked `processing` is failed with
  "Interrupted by a server restart" and can be re-run. Generated tiles stay on
  disk. Set `QUEUE_BACKEND=rq` with Redis when you need jobs to outlive the
  process.
- **The tiles ZIP is built to disk before download.** Correct and ZIP64-safe,
  but it needs free space roughly equal to the pyramid. A free-disk check runs
  first and refuses with a clear message rather than filling the volume.
- **`gdal2tiles` progress parsing depends on its stdout format**, which is not
  a stable contract across GDAL releases. It is isolated in one class with unit
  tests, and job success is decided by output validation rather than by
  progress reaching 100 — so a parsing regression degrades the progress bar
  without ever producing a false success.

---

## Roadmap

MVP does exactly one path: `GeoTIFF → XYZ → internal tile server`. The
architecture is built around `INPUT → PIPELINE → OUTPUT → PUBLISHER` so the
rest land as new pipelines rather than redesigns — batch processing, COG,
reprojection, MBTiles, PMTiles, orthophoto repair, and Cesium terrain. See
[the PRD](docs/PRD.md#23-post-mvp-roadmap).
