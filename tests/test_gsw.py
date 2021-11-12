"""Tests for GSW module."""

import os
import tempfile

import pytest
import rasterio
import requests
from geohealthaccess.gsw import GSW, preprocess
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely import wkt


@pytest.fixture(scope="module")
def gsw():
    return GSW()


def test_gsw_checkproduct(gsw):
    with pytest.raises(ValueError):
        gsw._checkproduct("random_product_name")


@pytest.mark.parametrize(
    "lat, lon, locid",
    [
        (40, 30, "30E_40N"),
        (40.1, 30.1, "30E_50N"),
        (-40.1, 30.1, "30E_40S"),
        (-0.1, 0.1, "0E_0N"),
    ],
)
def test_gsw_location_id(gsw, lat, lon, locid):
    assert gsw.location_id(lat, lon) == locid


def test_gsw_spatial_index(gsw):
    assert len(gsw.sindex) == 504
    assert "50E_50N" in gsw.sindex.index
    assert gsw.sindex.is_valid.all()
    assert gsw.sindex.unary_union.bounds == (-180, -60, 180, 80)


def test_gsw_search(gsw, madagascar, senegal):
    assert sorted(gsw.search(madagascar)) == ["40E_10S", "40E_20S", "50E_10S"]
    assert sorted(gsw.search(senegal)) == ["20W_20N"]


@pytest.mark.parametrize(
    "tile, product, url",
    [
        ("30W_20N", "occurrence", "occurrence/occurrence_30W_20N_v1_1.tif"),
        ("50E_20S", "seasonality", "seasonality/seasonality_50E_20S_v1_1.tif"),
        ("180W_20S", "transitions", "transitions/transitions_180W_20S_v1_1.tif"),
    ],
)
def test_gsw_url(gsw, tile, product, url):
    BASE_URL = "https://storage.googleapis.com/global-surface-water/downloads2/"
    assert gsw.url(tile, product) == BASE_URL + url


def test_gsw_download(gsw, monkeypatch):
    def mockreturn(self, chunk_size):
        return [b"", b"", b""]

    monkeypatch.setattr(requests.Response, "iter_content", mockreturn)

    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        tile = "40E_20N"
        gsw.download(tile, "seasonality", tmp_dir)
        assert os.path.isfile(os.path.join(tmp_dir, "seasonality_40E_20N_v1_1.tif"))


def test_gsw_preprocess():
    src_dir = resource_filename(__name__, "data/gsw-raw-data")
    with open(resource_filename(__name__, "data/djibouti.wkt")) as f:
        geom = wkt.load(f)
    crs = CRS.from_epsg(3857)
    res = 100
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        dst_file = os.path.join(tmp_dir, "water.tif")
        preprocess(src_dir, dst_file, crs, res, geom)
        with rasterio.open(dst_file) as src:
            assert src.transform.a == res
            assert src.crs == crs
            data = src.read(1, masked=True)
            assert data.min() >= 0
            assert data.max() <= 12
