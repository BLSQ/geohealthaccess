"""Test worldpop module."""

import os
import tempfile

import pytest

from geohealthaccess.worldpop import WorldPop, clean_datadir, parse_filename


@pytest.fixture
def worldpop(scope="module"):
    wp = WorldPop()
    wp.login()
    return wp


@pytest.mark.remote
def test_worldpop_login():
    wp = WorldPop()
    wp.login()
    assert wp.ftp.lastresp == "230"


@pytest.mark.remote
def test_worldpop_logout():
    wp = WorldPop()
    wp.login()
    wp.logout()
    assert wp.ftp.lastresp == "221"


@pytest.mark.remote
def test_worldpop_available_years(worldpop):
    years = worldpop.available_years()
    assert len(years) >= 21
    assert 2020 in years
    assert sorted(years) == years


@pytest.mark.remote
def test_worldpop_url(worldpop):
    burundi2000 = (
        "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/"
        "2000/BDI/bdi_ppp_2000.tif"
    )
    assert worldpop.url("BDI", 2000) == burundi2000
    assert worldpop.url("BDI", 2000) == worldpop.url("bdi", "2000")


@pytest.mark.remote
def test_worldpop_download(worldpop):
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = worldpop.download("TON", tmpdir, year=2020)
        assert os.path.isfile(fpath)
        mtime = os.path.getmtime(fpath)
        # should not be downloaded again
        worldpop.download("TON", tmpdir, year=2020, overwrite=False)
        assert os.path.getmtime(fpath) == mtime
        # should be downloaded again
        worldpop.download("TON", tmpdir, year=2020, overwrite=True)
        assert os.path.getmtime(fpath) != mtime


@pytest.mark.remote
def test_worldpop_download_size(worldpop):
    assert worldpop.download_size("BDI", 2000) == 13629694


def test_parse_filename():
    wpfile = parse_filename("mdg_ppp_2020.tif")
    assert wpfile.country == "mdg"
    assert wpfile.datatype == "ppp"
    assert wpfile.year == 2020


def test__clean_datadir():
    # Create empty files in a temporary directory
    RASTERS = [
        "ton_ppp_2015.tif",
        "ton_ppp_2016_UNadj.tif",
        "ton_ppp_2018.tif",
        "mdg_ppp_2015.tif",
        "mdg_ppp_2017.tif",
    ]
    with tempfile.TemporaryDirectory() as tmpdir:

        # create empty files
        for raster in RASTERS:
            open(os.path.join(tmpdir, raster), "a").close()

        clean_datadir(tmpdir)
        remaining = os.listdir(tmpdir)

        expected = ["ton_ppp_2016_UNadj.tif", "ton_ppp_2018.tif", "mdg_ppp_2017.tif"]
        assert set(remaining) == set(expected)
