"""API tests — auth, upload validation, path-traversal safety, storage paths,
and a full upload -> tile -> publish -> serve round trip.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pytest

from app import create_app
from app.datasets import is_valid_slug, slugify
from app.models import ACTIVE_DATASET_STATUSES, Dataset, ProcessingJob, db
from app.storage import PathTraversal, safe_join

TIFF_LE = b"II*\x00"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "0")

    class TestConfig:
        from datetime import timedelta
        SECRET_KEY = "test"
        JWT_SECRET_KEY = "test-jwt"
        JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        CORS_ORIGINS = "*"
        STORAGE_ROOT = tmp_path / "storage"
        TILE_PUBLIC_BASE = "http://localhost:9005/tiles"
        GDAL_ROOT = ""
        GDAL2TILES_PATH = ""
        GDAL2TILES_PROCESSES = 2
        MAX_UPLOAD_MB = 64
        MAX_RASTER_PIXELS = 6_000_000_000
        MAX_CONCURRENT_RASTER_JOBS = 2
        MIN_FREE_DISK_GB = 0
        JOB_TIMEOUT_MINUTES = 30
        QUEUE_BACKEND = "thread"
        DEMO_MODE = False
        ADMIN_USERNAME = "admin"
        ADMIN_PASSWORD = "admin"
        ADMIN_EMAIL = "admin@test.local"
        PORT = 9005
        DEBUG = False
        SERVICE_NAME = "rasterforge-test"
        MAX_CONTENT_LENGTH = 64 * 1024 * 1024
        TESTING = True

    application = create_app(TestConfig, start_queue=False)
    yield application
    application.extensions["raster_queue"].shutdown(wait=False)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def auth(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert res.status_code == 200, res.get_json()
    token = res.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def real_geotiff(tmp_path_factory) -> Path:
    """A genuine 4-band RGBA GeoTIFF with NoData=0 — the PRD's problem case."""
    from raster.gdal_runner import GdalRunner, find_gdal_tool

    out_dir = tmp_path_factory.mktemp("raster")
    raw = out_dir / "raw.tif"
    final = out_dir / "ortho.tif"
    ulx, uly, px, size = 322000.0, 4160000.0, 0.068, 1024

    runner = GdalRunner()
    rc, out = runner.run_capture([
        str(find_gdal_tool("gdal_create")),
        "-outsize", str(size), str(size), "-bands", "4",
        "-burn", "120", "-burn", "90", "-burn", "60", "-burn", "255",
        "-a_srs", "EPSG:32652",
        "-a_ullr", str(ulx), str(uly), str(ulx + size * px), str(uly - size * px),
        "-a_nodata", "0", str(raw),
    ])
    assert rc == 0, out
    rc, out = GdalRunner().run_capture([
        str(find_gdal_tool("gdal_translate")),
        "-colorinterp", "red,green,blue,alpha",
        "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE",
        str(raw), str(final),
    ])
    assert rc == 0, out
    return final


# --------------------------------------------------------------------------
# Slugs
# --------------------------------------------------------------------------

def test_slugify_ascii_name():
    assert slugify("Main Event Site", "8c7bc1d0-e3f1-4a2b-9c8d-1e2f3a4b5c6d") == "main-event-site"


def test_slugify_korean_falls_back_to_short_id():
    """Korean ASCII-folds to nothing, so the slug must come from the id."""
    assert slugify("메인행사장", "8c7bc1d0-e3f1-4a2b-9c8d-1e2f3a4b5c6d") == "ds-8c7bc1d0"


def test_slugify_strips_punctuation_and_collapses_hyphens():
    assert slugify("Site #3 -- North!!", "abcdef12-0000-0000-0000-000000000000") == "site-3-north"


@pytest.mark.parametrize("bad", ["Has Space", "UPPER", "trailing-", "-leading", "dou--ble", ""])
def test_rejects_invalid_slugs(bad):
    assert not is_valid_slug(bad)


# --------------------------------------------------------------------------
# Path safety
# --------------------------------------------------------------------------

def test_safe_join_allows_normal_tile_path(tmp_path):
    assert safe_join(tmp_path, "14", "1", "2.png") == (tmp_path / "14" / "1" / "2.png").resolve()


@pytest.mark.parametrize("parts", [
    ("..", "..", "etc"),
    ("14", "..", "..", "source"),
    ("/etc/passwd",),
    ("C:/Windows/system32",),
    ("14", "1", "../../../source/original.tif"),
    ("....//y.png",),
])
def test_safe_join_rejects_traversal(tmp_path, parts):
    with pytest.raises(PathTraversal):
        safe_join(tmp_path, *parts)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def test_health_needs_no_auth(client):
    assert client.get("/api/health").status_code == 200


def test_upload_requires_auth(client):
    assert client.post("/api/datasets").status_code == 401


def test_dataset_list_requires_auth(client):
    assert client.get("/api/datasets").status_code == 401


def test_login_rejects_bad_password(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_login_returns_access_token_not_token(client):
    """Regression: the starter template returned {"token"} while its own
    client read `access_token`, so the token was silently never stored."""
    body = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin"}
    ).get_json()
    assert "access_token" in body and body["user"]["role"] == "admin"


def test_me_returns_the_logged_in_user(client, auth):
    assert client.get("/api/auth/me", headers=auth).get_json()["username"] == "admin"


# --------------------------------------------------------------------------
# Upload validation
# --------------------------------------------------------------------------

def test_upload_rejects_wrong_extension(client, auth):
    res = client.post(
        "/api/datasets",
        data={"file": (io.BytesIO(TIFF_LE + b"x" * 100), "photo.png")},
        headers=auth, content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "unsupported_file"


def test_upload_rejects_non_tiff_content_despite_tif_extension(client, auth):
    """The filename is a claim; the magic bytes are the evidence."""
    res = client.post(
        "/api/datasets",
        data={"file": (io.BytesIO(b"totally not a tiff"), "sneaky.tif")},
        headers=auth, content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "unsupported_file"


def test_upload_rejects_tiff_header_that_gdal_cannot_open(client, auth):
    """Correct magic bytes but garbage content — only gdalinfo catches this."""
    res = client.post(
        "/api/datasets",
        data={"file": (io.BytesIO(TIFF_LE + b"\x00" * 512), "broken.tif")},
        headers=auth, content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] in ("corrupted_raster", "missing_crs")


def test_rejected_upload_leaves_no_dataset_row(client, auth, app):
    client.post(
        "/api/datasets",
        data={"file": (io.BytesIO(b"nope"), "x.tif")},
        headers=auth, content_type="multipart/form-data",
    )
    with app.app_context():
        assert Dataset.query.count() == 0


# --------------------------------------------------------------------------
# Full round trip
# --------------------------------------------------------------------------

def _wait_for_job(client, auth, job_id: str, timeout: float = 300.0) -> dict:
    """Poll until the job reaches a terminal state.

    The job is run by the real queue (create_tile_job submits it), so calling
    run_job() here as well would execute it twice concurrently -- two GDAL
    processes writing the same tile directory, which corrupts the output and
    fails in confusing ways.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}", headers=auth).get_json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.25)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def _upload(client, auth, path: Path, name="메인행사장"):
    with path.open("rb") as fh:
        return client.post(
            "/api/datasets",
            data={"file": (io.BytesIO(fh.read()), "ortho.tif"), "display_name": name},
            headers=auth, content_type="multipart/form-data",
        )


def test_upload_parses_metadata_and_recommends_zoom(client, auth, real_geotiff):
    res = _upload(client, auth, real_geotiff)
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    meta = body["metadata"]

    assert body["status"] == "ready"
    assert body["slug"].startswith("ds-"), "Korean name must fall back to an id slug"
    assert meta["epsg"] == 32652
    assert meta["band_count"] == 4
    assert meta["has_alpha"] is True
    assert meta["recommended_max_zoom"] == 21
    assert meta["nodata_warning"] and "Alpha" in meta["nodata_warning"]


def test_job_rejects_out_of_range_zoom(client, auth, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()
    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 99}, headers=auth,
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "invalid_request"


def test_job_rejects_unknown_resampling(client, auth, real_geotiff):
    """Resampling reaches a GDAL argument, so it must come from a fixed enum."""
    ds = _upload(client, auth, real_geotiff).get_json()
    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 16, "resampling": "; rm -rf /"}, headers=auth,
    )
    assert res.status_code == 400


@pytest.mark.slow
def test_full_upload_tile_publish_serve_roundtrip(client, auth, app, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()

    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 17, "nodata_mode": "auto"}, headers=auth,
    )
    assert res.status_code == 201, res.get_json()
    job = _wait_for_job(client, auth, res.get_json()["id"])
    assert job["status"] == "completed", (job["error_code"], job["error_message"])
    assert job["progress"] == 100

    detail = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()
    assert detail["status"] == "completed"

    output = detail["published_output"]
    assert output["is_published"] is True
    assert output["tile_count"] > 0
    assert output["normalised"] is True, "alpha + NoData=0 must trigger normalisation"
    assert output["public_url_template"].endswith("/{z}/{x}/{y}.png")

    # A real tile must be served from the public route.
    tiles_root = Path(app.config["STORAGE_ROOT"]) / "datasets" / ds["id"] / "output" / "tiles"
    sample = next(tiles_root.rglob("*.png"))
    z, x, y = sample.parent.parent.name, sample.parent.name, sample.name
    served = client.get(f"/tiles/{detail['slug']}/{z}/{x}/{y}")
    assert served.status_code == 200
    assert served.data.startswith(b"\x89PNG")


@pytest.mark.slow
@pytest.mark.parametrize("rest", [
    "../../../source/original.tif",
    "../../source/original.tif",
    "....//original.tif",
    "..%2f..%2foriginal.tif",
])
def test_tile_route_refuses_traversal(client, auth, app, real_geotiff, rest):
    """The tile route is public; it must not reach the source GeoTIFF."""
    ds = _upload(client, auth, real_geotiff).get_json()
    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    )
    _wait_for_job(client, auth, res.get_json()["id"])

    slug = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()["slug"]
    assert client.get(f"/tiles/{slug}/14/1/{rest}").status_code == 404


def test_unpublished_dataset_serves_no_tiles(client, auth, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()
    assert client.get(f"/tiles/{ds['slug']}/14/1/1.png").status_code == 404


# --------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------

def test_other_users_cannot_read_a_dataset(client, auth, app, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()

    client.post("/api/admin/users", json={
        "username": "bob", "password": "bobpass", "role": "user",
    }, headers=auth)
    token = client.post(
        "/api/auth/login", json={"username": "bob", "password": "bobpass"}
    ).get_json()["access_token"]
    bob = {"Authorization": f"Bearer {token}"}

    assert client.get(f"/api/datasets/{ds['id']}", headers=bob).status_code == 403
    assert client.delete(f"/api/datasets/{ds['id']}", headers=bob).status_code == 403
    assert client.get("/api/datasets", headers=bob).get_json() == []


def test_non_admin_cannot_read_admin_stats(client, auth):
    client.post("/api/admin/users", json={
        "username": "carol", "password": "carolpass", "role": "user",
    }, headers=auth)
    token = client.post(
        "/api/auth/login", json={"username": "carol", "password": "carolpass"}
    ).get_json()["access_token"]
    res = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


# --------------------------------------------------------------------------
# Restart recovery
# --------------------------------------------------------------------------

def test_restart_recovery_fails_stuck_jobs(client, auth, app, real_geotiff):
    """In-process jobs cannot survive a restart, so a job left at 'processing'
    must be failed honestly rather than hang forever."""
    ds = _upload(client, auth, real_geotiff).get_json()
    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    )
    job_id = res.get_json()["id"]

    with app.app_context():
        job = db.session.get(ProcessingJob, job_id)
        job.status = "processing"
        db.session.commit()

    from app.jobs import recover_interrupted_jobs
    assert recover_interrupted_jobs(app) == 1

    with app.app_context():
        job = db.session.get(ProcessingJob, job_id)
        assert job.status == "failed"
        assert "restart" in job.error_message.lower()
        assert job.dataset.status == "ready"


# --------------------------------------------------------------------------
# Resource protection
# --------------------------------------------------------------------------

def test_job_refused_when_disk_is_short(client, auth, app, real_geotiff, monkeypatch):
    """PRD §18: estimate the output, check free space, refuse before starting
    rather than filling the volume mid-job."""
    ds = _upload(client, auth, real_geotiff).get_json()
    app.config["MIN_FREE_DISK_GB"] = 10_000_000  # demand more space than exists

    res = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 18}, headers=auth,
    )
    assert res.status_code == 507
    assert res.get_json()["error_code"] == "insufficient_disk"

    with app.app_context():
        assert ProcessingJob.query.count() == 0, "a refused job must not be recorded"


def test_second_job_on_same_dataset_is_refused(client, auth, app, real_geotiff):
    """Two jobs writing one tile directory corrupt each other's output."""
    ds = _upload(client, auth, real_geotiff).get_json()
    first = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    )
    assert second.status_code == 409
    assert second.get_json()["error_code"] == "job_conflict"
    _wait_for_job(client, auth, first.get_json()["id"])


def test_dataset_cannot_be_deleted_while_a_job_runs(client, auth, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    ).get_json()

    res = client.delete(f"/api/datasets/{ds['id']}", headers=auth)
    assert res.status_code == 409
    _wait_for_job(client, auth, job["id"])


def test_cancelled_job_is_recorded_and_frees_the_dataset(client, auth, real_geotiff):
    """A terminal job must never leave its dataset looking busy.

    Regression: the cancel route used to write the terminal state based on a
    stale `queued` read while the worker was concurrently committing
    `processing`. The worker's write landed last, stranding the dataset at
    `processing` with a `cancelled` job — a dataset that looks busy forever
    and refuses every new job with `job_conflict`.
    """
    ds = _upload(client, auth, real_geotiff).get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    ).get_json()

    client.post(f"/api/jobs/{job['id']}/cancel", headers=auth)
    final = _wait_for_job(client, auth, job["id"])
    assert final["status"] in ("cancelled", "completed")  # may finish first; it is tiny

    # Give any still-unwinding worker a moment, then assert the invariant.
    deadline = time.time() + 20
    while time.time() < deadline:
        detail = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()
        if detail["status"] not in ACTIVE_DATASET_STATUSES:
            break
        time.sleep(0.25)

    assert detail["status"] not in ACTIVE_DATASET_STATUSES, (
        f"terminal job left dataset at {detail['status']!r}"
    )
    assert detail["status"] in ("ready", "completed")

    # And the dataset must accept work again.
    again = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    )
    assert again.status_code == 201, again.get_json()
    _wait_for_job(client, auth, again.get_json()["id"])


@pytest.mark.parametrize("run", range(6))
def test_cancel_during_startup_never_strands_the_dataset(client, auth, real_geotiff, run):
    """Cancel immediately, with no delay, so the request collides with worker
    startup — the exact window the old code lost."""
    ds = _upload(client, auth, real_geotiff, name=f"race-{run}").get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 16}, headers=auth,
    ).get_json()
    client.post(f"/api/jobs/{job['id']}/cancel", headers=auth)

    final = _wait_for_job(client, auth, job["id"])
    assert final["status"] in ("cancelled", "completed")

    deadline = time.time() + 20
    while time.time() < deadline:
        detail = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()
        if detail["status"] not in ACTIVE_DATASET_STATUSES:
            break
        time.sleep(0.25)
    assert detail["status"] not in ACTIVE_DATASET_STATUSES, (
        f"run {run}: dataset stranded at {detail['status']!r} "
        f"with job {final['status']!r}"
    )


# --------------------------------------------------------------------------
# Publishing
# --------------------------------------------------------------------------

def test_publish_retry_does_not_rerun_processing(client, auth, app, real_geotiff):
    """A publish failure must be repairable without redoing the expensive work."""
    ds = _upload(client, auth, real_geotiff).get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 16}, headers=auth,
    ).get_json()
    _wait_for_job(client, auth, job["id"])

    with app.app_context():
        before = db.session.get(Dataset, ds["id"]).outputs[0].id

    res = client.post(f"/api/datasets/{ds['id']}/publish", headers=auth)
    assert res.status_code == 200
    assert res.get_json()["status"] == "completed"

    with app.app_context():
        d = db.session.get(Dataset, ds["id"])
        assert len(d.jobs) == 1, "republishing must not create a new processing job"
        assert d.outputs[0].id == before, "republishing must reuse the existing output"


def test_renaming_updates_the_published_url(client, auth, real_geotiff):
    """The slug is in the advertised URL, so a rename must republish it."""
    ds = _upload(client, auth, real_geotiff).get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    ).get_json()
    _wait_for_job(client, auth, job["id"])

    renamed = client.patch(
        f"/api/datasets/{ds['id']}", json={"slug": "main-event-site"}, headers=auth,
    ).get_json()
    assert renamed["slug"] == "main-event-site"

    detail = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()
    assert "main-event-site" in detail["published_output"]["public_url_template"]
    assert client.get("/tiles/main-event-site/14/1/1.png").status_code in (200, 404)


def test_internal_slug_resolution_for_nginx(client, auth, real_geotiff):
    """Nginx's auth_request needs slug -> dataset id to serve tiles from the
    shared volume (Option A in infra/nginx/rasterforge.conf)."""
    ds = _upload(client, auth, real_geotiff).get_json()
    job = client.post(
        f"/api/datasets/{ds['id']}/tile-jobs",
        json={"min_zoom": 14, "max_zoom": 15}, headers=auth,
    ).get_json()
    _wait_for_job(client, auth, job["id"])

    slug = client.get(f"/api/datasets/{ds['id']}", headers=auth).get_json()["slug"]
    res = client.get(f"/api/internal/resolve-slug?slug={slug}")
    assert res.status_code == 200
    assert res.headers["X-Dataset-Id"] == ds["id"]


def test_internal_slug_resolution_404s_for_unpublished_and_unknown(client, auth, real_geotiff):
    ds = _upload(client, auth, real_geotiff).get_json()
    assert client.get(f"/api/internal/resolve-slug?slug={ds['slug']}").status_code == 404
    assert client.get("/api/internal/resolve-slug?slug=nope").status_code == 404
    assert client.get("/api/internal/resolve-slug").status_code == 404
