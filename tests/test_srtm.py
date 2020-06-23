"""Tests for SRTM module."""

import os
import tempfile

import pytest

from geohealthaccess.srtm import SRTM


@pytest.fixture(scope="module")
def srtm():
    """Authentified EarthData session."""
    srtm_ = SRTM()
    srtm_.authentify(
        os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    )
    return srtm_


@pytest.mark.remote
def test_srtm_authenticity_token():
    srtm = SRTM()
    assert srtm.authenticity_token
    assert srtm.authenticity_token.endswith("==")


@pytest.mark.remote
def test_srtm_authentify():
    srtm = SRTM()
    srtm.authentify(
        os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    )


@pytest.mark.remote
def test_srtm_logged_in(srtm):
    srtm_ = SRTM()
    assert not srtm_.logged_in
    assert srtm.logged_in


def test_srtm_spatial_index():
    srtm = SRTM()
    sindex = srtm.spatial_index()
    assert len(sindex) == 14295
    assert sindex.is_valid.all()
    assert "S56W070.SRTMGL1.hgt.zip" in sindex.dataFile.values


def test_srtm_search(senegal, madagascar):
    srtm = SRTM()
    sen_tiles = srtm.search(senegal)
    mdg_tiles = srtm.search(madagascar)
    assert len(sen_tiles) == 29
    assert len(mdg_tiles) == 75
    assert sorted(mdg_tiles)[0] == "S12E049.SRTMGL1.hgt.zip"
    assert sorted(sen_tiles)[0] == "N12W012.SRTMGL1.hgt.zip"


@pytest.mark.remote
def test_srtm_download(srtm):
    TILE = "N12W012.SRTMGL1.hgt.zip"
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = srtm.download(TILE, tmpdir)
        assert os.path.isfile(fpath)
        mtime = os.path.getmtime(fpath)
        # should not be downloaded again
        srtm.download(TILE, tmpdir, overwrite=False)
        assert os.path.getmtime(fpath) == mtime
        # should be downloaded again
        srtm.download(TILE, tmpdir, overwrite=True)
        assert os.path.getmtime(fpath) != mtime


@pytest.mark.remote
def test_srtm_download_size(srtm):
    TILE = "N12W012.SRTMGL1.hgt.zip"
    assert srtm.download_size(TILE) == 10087801
