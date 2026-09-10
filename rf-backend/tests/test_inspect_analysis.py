"""Tests for gdalinfo parsing, NoData decisions and zoom recommendation.

All pure — no GDAL required — so the trickiest logic in the product stays
testable and fast.
"""
import pytest

from raster.analysis import (
    decide_nodata,
    estimate_tile_count,
    native_zoom_for_resolution,
    recommend_max_zoom,
)
from raster.inspect import parse_gdalinfo

UTM52N_WKT = (
    'PROJCRS["WGS 84 / UTM zone 52N",BASEGEOGCRS["WGS 84",'
    'DATUM["World Geodetic System 1984",ELLIPSOID["WGS 84",6378137,298.257223563,'
    'LENGTHUNIT["metre",1]]],ID["EPSG",4326]],CONVERSION["UTM zone 52N"],'
    'CS[Cartesian,2],AXIS["(E)",east,LENGTHUNIT["metre",1]],'
    'AXIS["(N)",north,LENGTHUNIT["metre",1]],ID["EPSG",32652]]'
)

WGS84_WKT = (
    'GEOGCRS["WGS 84",DATUM["World Geodetic System 1984",'
    'ELLIPSOID["WGS 84",6378137,298.257223563,LENGTHUNIT["metre",1]]],'
    'CS[ellipsoidal,2],AXIS["latitude",north,ANGLEUNIT["degree",0.0174532925199433]],'
    'AXIS["longitude",east,ANGLEUNIT["degree",0.0174532925199433]],ID["EPSG",4326]]'
)

EXTENT = {
    "type": "Polygon",
    "coordinates": [[
        [126.90, 37.60], [126.94, 37.60], [126.94, 37.57], [126.90, 37.57], [126.90, 37.60],
    ]],
}


def rgba_nodata0():
    return {
        "driverShortName": "GTiff",
        "size": [48567, 25143],
        "coordinateSystem": {"wkt": UTM52N_WKT},
        "geoTransform": [321000.0, 0.068, 0.0, 4165000.0, 0.0, -0.068],
        "wgs84Extent": EXTENT,
        "stac": {"proj:epsg": 32652},
        "bands": [
            {"band": 1, "type": "Byte", "colorInterpretation": "Red", "noDataValue": 0},
            {"band": 2, "type": "Byte", "colorInterpretation": "Green", "noDataValue": 0},
            {"band": 3, "type": "Byte", "colorInterpretation": "Blue", "noDataValue": 0},
            {"band": 4, "type": "Byte", "colorInterpretation": "Alpha", "noDataValue": 0},
        ],
    }


def rgb_clean():
    d = rgba_nodata0()
    d["bands"] = [
        {"band": 1, "type": "Byte", "colorInterpretation": "Red"},
        {"band": 2, "type": "Byte", "colorInterpretation": "Green"},
        {"band": 3, "type": "Byte", "colorInterpretation": "Blue"},
    ]
    return d


def rgb_nodata_no_alpha():
    d = rgb_clean()
    for b in d["bands"]:
        b["noDataValue"] = 0
    return d


def geographic_raster():
    return {
        "driverShortName": "GTiff",
        "size": [1000, 1000],
        "coordinateSystem": {"wkt": WGS84_WKT},
        # ~0.5 m at this latitude
        "geoTransform": [126.90, 5.6e-06, 0.0, 37.60, 0.0, -5.6e-06],
        "wgs84Extent": EXTENT,
        "bands": [{"band": 1, "type": "Byte", "colorInterpretation": "Gray"}],
    }


# --- parsing --------------------------------------------------------------

def test_parses_dimensions_driver_and_bands():
    info = parse_gdalinfo(rgba_nodata0())
    assert (info.width, info.height) == (48567, 25143)
    assert info.driver == "GTiff"
    assert info.band_count == 4
    assert info.has_alpha is True
    assert info.bands[3].is_alpha is True
    assert info.bands[0].is_alpha is False


def test_parses_epsg_from_stac():
    assert parse_gdalinfo(rgba_nodata0()).epsg == 32652


def test_parses_epsg_from_wkt_when_stac_absent():
    d = rgba_nodata0()
    del d["stac"]
    # The outermost authority wins — not the nested BASEGEOGCRS EPSG:4326.
    assert parse_gdalinfo(d).epsg == 32652


def test_parses_crs_name():
    assert parse_gdalinfo(rgba_nodata0()).crs_name == "WGS 84 / UTM zone 52N"


def test_parses_pixel_size_and_gsd_for_projected_crs():
    info = parse_gdalinfo(rgba_nodata0())
    assert round(info.pixel_size_x, 4) == 0.068
    assert round(info.pixel_size_y, 4) == 0.068
    assert info.is_geographic is False
    assert round(info.gsd_m, 4) == 0.068  # metre-based CRS: 1:1


def test_converts_degrees_to_metres_for_geographic_crs():
    info = parse_gdalinfo(geographic_raster())
    assert info.is_geographic is True
    # 5.6e-06 deg * 111319 m/deg * cos(37.585) ~= 0.494 m
    assert 0.45 < info.gsd_m < 0.55


def test_computes_bounds_and_center():
    info = parse_gdalinfo(rgba_nodata0())
    assert info.bounds_wgs84 == (126.90, 37.57, 126.94, 37.60)
    assert info.center_wgs84 == pytest.approx((126.92, 37.585))


def test_collects_nodata_values():
    assert parse_gdalinfo(rgba_nodata0()).nodata_values == [0.0, 0.0, 0.0, 0.0]
    assert parse_gdalinfo(rgb_clean()).nodata_values == [None, None, None]


# --- NoData decision ------------------------------------------------------

def test_auto_normalises_when_alpha_and_nodata_zero():
    d = decide_nodata(parse_gdalinfo(rgba_nodata0()), "auto")
    assert d.normalise is True
    assert d.warning and "Alpha band" in d.warning


def test_auto_leaves_clean_raster_alone():
    d = decide_nodata(parse_gdalinfo(rgb_clean()), "auto")
    assert d.normalise is False
    assert d.warning is None


def test_auto_preserves_nodata_when_it_is_the_only_transparency():
    d = decide_nodata(parse_gdalinfo(rgb_nodata_no_alpha()), "auto")
    assert d.normalise is False
    assert d.warning is None


def test_preserve_never_normalises_but_still_warns():
    d = decide_nodata(parse_gdalinfo(rgba_nodata0()), "preserve")
    assert d.normalise is False
    assert d.warning is not None


def test_remove_always_normalises():
    assert decide_nodata(parse_gdalinfo(rgb_clean()), "remove").normalise is True


# --- zoom -----------------------------------------------------------------

def test_native_zoom_for_68mm_near_seoul():
    assert native_zoom_for_resolution(0.068, 37.58) == 21


def test_native_zoom_clamped_to_22():
    assert native_zoom_for_resolution(0.0001, 37.58) == 22


def test_native_zoom_for_coarse_raster():
    assert native_zoom_for_resolution(30.0, 37.58) == 12


def test_recommend_max_zoom_uses_center_latitude():
    assert recommend_max_zoom(parse_gdalinfo(rgba_nodata0())) == 21


def test_recommend_max_zoom_none_without_pixel_size():
    d = rgba_nodata0()
    d["geoTransform"] = [0, 0, 0, 0, 0, 0]
    assert recommend_max_zoom(parse_gdalinfo(d)) is None


# --- tile estimate --------------------------------------------------------

def test_tile_estimate_grows_with_zoom():
    info = parse_gdalinfo(rgba_nodata0())
    assert estimate_tile_count(info, 14, 18) < estimate_tile_count(info, 14, 21)


def test_tile_estimate_zero_without_bounds():
    d = rgba_nodata0()
    del d["wgs84Extent"]
    assert estimate_tile_count(parse_gdalinfo(d), 14, 18) == 0
