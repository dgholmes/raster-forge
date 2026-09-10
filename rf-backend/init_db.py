"""Create tables and seed the admin account.

    python init_db.py

Safe to re-run; seeding is idempotent.
"""
from app import create_app
from app.auth import seed_admin_user
from app.models import Dataset, ProcessingJob, TileOutput, User, db
from raster.gdal_runner import gdal_diagnostics

app = create_app(start_queue=False)

with app.app_context():
    db.create_all()
    seed_admin_user()

    print("-" * 62)
    print("RasterForge database initialised.")
    print(f"  URI       {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"  Storage   {app.config['STORAGE_ROOT']}")
    print(f"  Users     {User.query.count()}"
          f"  (admin: {app.config['ADMIN_USERNAME']}/{app.config['ADMIN_PASSWORD']})")
    print(f"  Datasets  {Dataset.query.count()}")
    print(f"  Jobs      {ProcessingJob.query.count()}")
    print(f"  Outputs   {TileOutput.query.count()}")
    print("-" * 62)
    diag = gdal_diagnostics()
    print(f"  GDAL      {diag.get('install_root')}")
    print(f"  Can tile  {diag.get('can_tile')}")
    if diag.get("can_tile") != "yes":
        print("  [!] Tiling is unavailable. Install QGIS or set GDAL_ROOT.")
    print("-" * 62)
