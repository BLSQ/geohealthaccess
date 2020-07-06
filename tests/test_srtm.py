"""Tests for SRTM module."""

import os
import tempfile
import vcr

import pytest

from geohealthaccess.srtm import SRTM


@pytest.fixture(scope="module")
def unauthentified_srtm():
    """Non-authentified EarthData session."""
    return SRTM()


@vcr.use_cassette("tests/cassettes/srtm-authenticity-token.yaml")
def test_srtm_authenticity_token(unauthentified_srtm):
    unauthentified_srtm = SRTM()
    assert unauthentified_srtm.authenticity_token.endswith("==")


def test_srtm_authentification():
    srtm = SRTM()
    with vcr.use_cassette("tests/cassettes/srtm-authentification.yaml"):
        srtm.authentify(
            os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
        )
    with vcr.use_cassette("tests/cassettes/srtm-logged-in.yaml"):
        assert srtm.logged_in


@vcr.use_cassette("tests/cassettes/srtm-not-logged-in.yaml")
def test_srtm_not_logged_in(unauthentified_srtm):
    assert not unauthentified_srtm.logged_in


def test_srtm_spatial_index(unauthentified_srtm):
    sindex = unauthentified_srtm.spatial_index()
    assert len(sindex) == 14295
    assert sindex.is_valid.all()
    assert "S56W070.SRTMGL1.hgt.zip" in sindex.dataFile.values


def test_srtm_search(unauthentified_srtm, senegal, madagascar):
    sen_tiles = unauthentified_srtm.search(senegal)
    mdg_tiles = unauthentified_srtm.search(madagascar)
    assert len(sen_tiles) == 29
    assert len(mdg_tiles) == 75
    assert sorted(mdg_tiles)[0] == "S12E049.SRTMGL1.hgt.zip"
    assert sorted(sen_tiles)[0] == "N12W012.SRTMGL1.hgt.zip"


@vcr.use_cassette("tests/cassettes/srtm-N19W075.yaml", mode="none")
def test_srtm_download():
    srtm = SRTM()
    TILE = "N19W075.SRTMGL1.hgt.zip"
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = srtm.download(TILE, tmpdir)
        assert os.path.isfile(fpath)


@vcr.use_cassette("tests/cassettes/srtm-N12W012.yaml", mode="none")
def test_srtm_download_size():
    srtm = SRTM()
    TILE = "N12W012.SRTMGL1.hgt.zip"
    assert srtm.download_size(TILE) == 10087801
