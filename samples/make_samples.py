"""Generate synthetic GeoTIFFs for an end-to-end RasterForge test.

    python samples/make_samples.py

Needs only numpy + tifffile (no GDAL), so it runs on any dev machine. Writes
into samples/out/:

  01_seoul_cityhall_rgb_4326.tif   RGB, EPSG:4326, ~0.6 m/px around City Hall.
                                   The happy path: upload → inspect → tiles.
  02_yeouido_rgba_footprint_4326.tif
                                   RGBA with a rotated, drone-like footprint;
                                   outside it is alpha=0. Checks transparency
                                   (no black frame around the mosaic).
  03_gangnam_rgb_utmk_5179.tif     RGB, EPSG:5179 (Korea 2000 / UTM-K).
                                   Checks reprojection of a projected CRS.
  04_not_a_geotiff.tif             Plain text with a .tif name. The upload
                                   must be REJECTED (magic-byte check).

Every raster carries a red crosshair at its exact centre and coloured corner
markers, so misplacement on the basemap is obvious at a glance.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

OUT = Path(__file__).resolve().parent / "out"
RNG = np.random.default_rng(42)

# GeoKey ids (GeoTIFF spec)
GT_MODEL_TYPE, GT_RASTER_TYPE = 1024, 1025
GEOGRAPHIC_TYPE, GEOG_ANGULAR_UNITS = 2048, 2054
PROJECTED_CS_TYPE, PROJ_LINEAR_UNITS = 3072, 3076


def geotags(ulx: float, uly: float, sx: float, sy: float, epsg: int, projected: bool):
    """ModelPixelScale + ModelTiepoint + GeoKeyDirectory for a north-up raster."""
    if projected:
        keys = [(GT_MODEL_TYPE, 1), (GT_RASTER_TYPE, 1),
                (PROJECTED_CS_TYPE, epsg), (PROJ_LINEAR_UNITS, 9001)]
    else:
        keys = [(GT_MODEL_TYPE, 2), (GT_RASTER_TYPE, 1),
                (GEOGRAPHIC_TYPE, epsg), (GEOG_ANGULAR_UNITS, 9102)]
    directory = [1, 1, 0, len(keys)]
    for key, value in keys:
        directory += [key, 0, 1, value]
    return [
        (33550, "d", 3, (sx, sy, 0.0), True),
        (33922, "d", 6, (0.0, 0.0, 0.0, ulx, uly, 0.0), True),
        (34735, "H", len(directory), tuple(directory), True),
    ]


def smooth_noise(h: int, w: int, cell: int) -> np.ndarray:
    """Cheap value noise in [0, 1]: random grid, bilinearly upsampled."""
    gh, gw = h // cell + 2, w // cell + 2
    grid = RNG.random((gh, gw))
    y = np.linspace(0, gh - 1.001, h)
    x = np.linspace(0, gw - 1.001, w)
    y0, x0 = y.astype(int), x.astype(int)
    fy, fx = (y - y0)[:, None], (x - x0)[None, :]
    a = grid[y0][:, x0]
    b = grid[y0][:, x0 + 1]
    c = grid[y0 + 1][:, x0]
    d = grid[y0 + 1][:, x0 + 1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def aerial(h: int, w: int) -> np.ndarray:
    """Synthetic 'aerial photo': fields, a river, a road grid and buildings."""
    n = smooth_noise(h, w, 96) * 0.7 + smooth_noise(h, w, 12) * 0.3
    img = np.empty((h, w, 3), np.float32)
    # Vegetation ↔ bare soil, driven by the noise.
    img[..., 0] = 70 + 90 * n
    img[..., 1] = 110 + 60 * (1 - n)
    img[..., 2] = 60 + 40 * n

    yy, xx = np.mgrid[0:h, 0:w]
    # A meandering river.
    centre = h * 0.62 + np.sin(xx / w * 2 * np.pi * 1.5) * h * 0.06
    river = np.abs(yy - centre) < h * 0.035
    img[river] = (55, 95, 140)

    # Road grid.
    roads = ((xx % 256) < 10) | ((yy % 256) < 10)
    img[roads & ~river] = (120, 120, 118)

    # Buildings: grey/brown blocks inside the road cells.
    for _ in range(int(h * w / 9000)):
        bx, by = RNG.integers(0, w - 60), RNG.integers(0, h - 60)
        bw, bh = RNG.integers(14, 50, size=2)
        block = (slice(by, by + bh), slice(bx, bx + bw))
        if river[block].any() or roads[block].any():
            continue
        img[block] = RNG.integers(150, 215) + RNG.integers(-15, 15, size=3)

    img += RNG.normal(0, 4, img.shape)  # sensor grain
    return np.clip(img, 0, 255).astype(np.uint8)


def add_markers(img: np.ndarray) -> None:
    """Red centre crosshair + coloured 64 px corner squares (TL red, TR green,
    BL blue, BR yellow) so orientation errors are obvious."""
    h, w = img.shape[:2]
    cy, cx, t = h // 2, w // 2, max(4, w // 400)
    img[cy - t:cy + t, cx - w // 10:cx + w // 10, :3] = (230, 30, 30)
    img[cy - h // 10:cy + h // 10, cx - t:cx + t, :3] = (230, 30, 30)
    s = 64
    img[:s, :s, :3] = (230, 30, 30)
    img[:s, -s:, :3] = (30, 200, 30)
    img[-s:, :s, :3] = (30, 60, 230)
    img[-s:, -s:, :3] = (240, 220, 30)


def write(name: str, data: np.ndarray, tags, **kw) -> None:
    path = OUT / name
    tifffile.imwrite(
        path, data, photometric="rgb", tile=(256, 256),
        compression="zlib", extratags=tags, **kw,
    )
    print(f"  {path.name:40s} {data.shape[1]}x{data.shape[0]}  "
          f"{path.stat().st_size / 1e6:5.1f} MB")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    print(f"writing to {OUT}")

    # 01 — RGB, EPSG:4326, centred on Seoul City Hall (37.5663, 126.9779).
    size = 2560
    deg = 0.016  # ~1.4 km wide
    img = aerial(size, size)
    add_markers(img)
    write("01_seoul_cityhall_rgb_4326.tif", img,
          geotags(126.9779 - deg / 2, 37.5663 + deg / 2,
                  deg / size, deg / size, 4326, projected=False))

    # 02 — RGBA, rotated drone footprint over Yeouido (37.5260, 126.9250).
    size = 2048
    deg = 0.014
    rgb = aerial(size, size)
    yy, xx = np.mgrid[0:size, 0:size]
    ang = np.deg2rad(23)
    u = (xx - size / 2) * np.cos(ang) + (yy - size / 2) * np.sin(ang)
    v = -(xx - size / 2) * np.sin(ang) + (yy - size / 2) * np.cos(ang)
    inside = (np.abs(u) < size * 0.38) & (np.abs(v) < size * 0.27)
    rgba = np.dstack([rgb, np.where(inside, 255, 0).astype(np.uint8)])
    add_markers(rgba)
    rgba[~inside, 3] = 0
    write("02_yeouido_rgba_footprint_4326.tif", rgba,
          geotags(126.9250 - deg / 2, 37.5260 + deg / 2,
                  deg / size, deg / size, 4326, projected=False),
          extrasamples=[2])  # unassociated alpha

    # 03 — RGB, EPSG:5179 (UTM-K), 0.5 m/px around Gangnam Station.
    size = 2048
    res = 0.5
    cx, cy = 958_250.0, 1_944_400.0  # ≈ 37.498 N, 127.028 E (Gangnam Stn)
    img = aerial(size, size)
    add_markers(img)
    write("03_gangnam_rgb_utmk_5179.tif", img,
          geotags(cx - size * res / 2, cy + size * res / 2,
                  res, res, 5179, projected=True))

    # 04 — not a GeoTIFF at all.
    bad = OUT / "04_not_a_geotiff.tif"
    bad.write_text("This is plain text pretending to be a GeoTIFF.\n", encoding="utf-8")
    print(f"  {bad.name:40s} (text file - upload must be rejected)")


if __name__ == "__main__":
    main()
