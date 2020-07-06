"""Tests for GSW module."""

import os
import tempfile

import vcr
import pytest

from geohealthaccess.gsw import GSW


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


@vcr.use_cassette("tests/cassettes/gsw-180W_20S-extent.yaml")
def test_gsw_download():
    gsw = GSW()
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = gsw.download("180W_20S", "extent", tmpdir)
        assert os.path.isfile(fpath)
        assert os.path.getsize(fpath) > 1000
        mtime = os.path.getmtime(fpath)
        # should not be downloaded again
        gsw.download("180W_20S", "extent", tmpdir, overwrite=False)
        assert os.path.getmtime(fpath) == mtime
        # should be downloaded again
        gsw.download("180W_20S", "extent", tmpdir, overwrite=True)
        assert os.path.getmtime(fpath) != mtime


@vcr.use_cassette("tests/cassettes/gsw-30W_20N-extent-head.yaml")
def test_gsw_download_size():
    gsw = GSW()
    assert gsw.download_size("30W_20N", "extent") == 11137774
