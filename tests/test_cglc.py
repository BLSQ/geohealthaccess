"""Tests for cglc module."""

import os
from glob import glob
from tempfile import TemporaryDirectory
import tempfile

import numpy as np
import pytest
import rasterio
import requests
from shapely.geometry import Point
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely import wkt

from geohealthaccess import cglc


@pytest.fixture(scope="module")
def catalog():
    return cglc.CGLC()


def test_download_url(catalog):
    url = catalog.download_url("E000N00", "BuiltUp", 2019)
    assert url == (
        "https://s3-eu-west-1.amazonaws.com/vito.landcover.global/v3.0.1/2019/E000N00/"
        "E000N00_PROBAV_LC100_global_v3.0.1_2019-nrt_"
        "BuiltUp-CoverFraction-layer_EPSG-4326.tif"
    )

    with pytest.raises(ValueError):
        catalog.download_url("E000N00", "NotALabel", 2019)

    with pytest.raises(ValueError):
        catalog.download_url("E000N00", "BuiltUp", 2000)


def test_format_latlon(catalog):
    assert catalog.format_latlon(20, 30) == "E030N20"
    assert catalog.format_latlon(-40, -120) == "W120S40"


def test_search(catalog):
    with open(resource_filename(__name__, "data/madagascar.wkt")) as f:
        geom = wkt.load(f)
        tiles = sorted(catalog.search(geom))
        expected = sorted(["E040N00", "E040S20"])
        assert tiles == expected
    with open(resource_filename(__name__, "data/senegal.wkt")) as f:
        geom = wkt.load(f)
        tiles = sorted(catalog.search(geom))
        expected = sorted(["W020N20"])
        assert tiles == expected


def test_download(catalog):
    # dummy geometry covering 4 different CGLC tiles
    geom = Point(20, 0).buffer(0.1)
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        dst_file = os.path.join(tmp_dir, "tree.tif")
        catalog.download(geom=geom, label="Tree", dst_file=dst_file, year=2019)
        with rasterio.open(dst_file) as src:
            data = src.read(1, masked=True)
            assert data.min() >= 0
            assert data.max() <= 100
            assert data.shape == (201, 201)


def test_preprocess(catalog):
    src_dir = resource_filename(__name__, "data/cglc-raw-data")
    print(src_dir)
    geom = Point(20, 0).buffer(0.1)
    crs = CRS.from_epsg(3857)
    res = 500
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        cglc.preprocess(src_dir, tmp_dir, geom, crs, res)
        for label in catalog.LABELS:
            src_file = os.path.join(tmp_dir, f"landcover_{label}.tif")
            with rasterio.open(src_file) as src:
                assert src.crs == crs
                data = src.read(1, masked=True)
                assert data.min() >= 0
                assert data.max() <= 100
