"""Tests for SRTM module."""

import os
import tempfile

import pytest
import rasterio
from geohealthaccess.srtm import SRTM, preprocess
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely.geometry import Point


@pytest.fixture(scope="module")
def geom():
    """Small geometry that need 4 SRTM tiles to be covered."""
    p = Point(20, 0)
    return p.buffer(0.1, resolution=2)


def test_srtm_search(geom):
    catalog = SRTM()

    expected_tiles = [
        "N00E019.SRTMGL1.hgt.zip",
        "N00E020.SRTMGL1.hgt.zip",
        "S01E019.SRTMGL1.hgt.zip",
        "S01E020.SRTMGL1.hgt.zip",
    ]

    tiles = catalog.search(geom)
    assert sorted(expected_tiles) == sorted(tiles)


@pytest.mark.web
def test_srtm_download():
    catalog = SRTM()
    catalog.authentify(os.getenv("EARTHDATA_USERNAME"), os.getenv("EARTHDATA_PASSWORD"))
    tile = "N37E011.SRTMGL1.hgt.zip"
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        catalog.download(tile, tmp_dir, show_progress=False)
        assert os.path.isfile(os.path.join(tmp_dir, "N37E011.SRTMGL1.hgt.zip"))


def test_preprocess(geom):
    src_dir = resource_filename(__name__, "data/srtm-raw-data")
    crs = CRS.from_epsg(3857)
    res = 500
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        elev, slope = preprocess(
            src_dir=src_dir,
            dst_elev=os.path.join(tmp_dir, "elev.tif"),
            dst_slope=os.path.join(tmp_dir, "slope.tif"),
            dst_crs=crs,
            dst_res=res,
            geom=geom,
        )
        with rasterio.open(elev) as src:
            assert src.transform.a == res
            assert src.crs == crs
            # assert src.nodata == -32767.0
            assert src.profile["dtype"] == "int16"
            data = src.read(1, masked=True)
            assert data.min() >= 300
            assert data.max() <= 400
        with rasterio.open(slope) as src:
            assert src.transform.a == res
            assert src.crs == crs
            # assert src.nodata == 9999
            assert src.profile["dtype"] == "float32"
            data = src.read(1, masked=True)
            assert data.min() >= 0
            assert data.max() <= 10
