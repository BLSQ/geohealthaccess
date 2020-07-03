"""Tests for utils module."""

import filecmp
import os
import tempfile
from ftplib import FTP

import pytest
import requests
import vcr
from pkg_resources import resource_filename

from geohealthaccess import utils

GITHUB = "https://raw.githubusercontent.com/BLSQ/geohealthaccess/master/"


@pytest.mark.parametrize(
    "size, expected",
    [(1024, "1.0 KB"), (542215845, "542.2 MB"), (845965254785, "846.0 GB")],
)
def test_human_readable_size(size, expected):
    assert utils.human_readable_size(size) == expected


@vcr.use_cassette("tests/cassettes/madagascar-geojson-head.yaml")
def test_size_from_url():
    url = GITHUB + "tests/data/madagascar.geojson"
    with requests.Session() as s:
        assert utils.size_from_url(s, url) == 22498


@vcr.use_cassette("tests/cassettes/madagascar-geojson-head.yaml")
def test_http_same_size():
    url = GITHUB + "tests/data/madagascar.geojson"
    path = resource_filename(__name__, "data/madagascar.geojson")
    with requests.Session() as s:
        assert utils.http_same_size(s, url, path)


@vcr.use_cassette("tests/cassettes/madagascar-geojson-head.yaml")
def test_http_not_same_size():
    url = GITHUB + "tests/data/madagascar.geojson"
    path = resource_filename(__name__, "data/madagascar.wkt")
    with requests.Session() as s:
        assert not utils.http_same_size(s, url, path)


def test_country_geometry():
    mdg = utils.country_geometry("mdg")
    assert mdg.is_valid
    assert not mdg.is_empty
    assert mdg.area == pytest.approx(51.07, 0.01)


def test_country_geometry_notfound():
    with pytest.raises(ValueError):
        utils.country_geometry("not_a_country")


@vcr.use_cassette("tests/cassettes/madagascar-geojson.yaml")
def test_download_from_url():
    """Use a local URL to avoid network calls."""
    url = GITHUB + "tests/data/madagascar.geojson"
    with tempfile.TemporaryDirectory(
        prefix="geohealthaccess_"
    ) as tmpdir, requests.Session() as s:
        # simple download
        path = utils.download_from_url(s, url, tmpdir, False)
        assert utils.http_same_size(s, url, path)
        mtime = os.path.getmtime(path)
        # should not be downloaded again (overwrite=False)
        utils.download_from_url(s, url, tmpdir, False, overwrite=False)
        assert mtime == os.path.getmtime(path)
        # should be downloaded again (overwrite=True)
        utils.download_from_url(s, url, tmpdir, False, overwrite=True)
        assert mtime != os.path.getmtime(path)


@pytest.mark.remote
def test_download_from_ftp():
    url = (
        "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2020/BDI/"
        "bdi_ppp_2020_metadata.html"
    )
    ftp = FTP("ftp.worldpop.org.uk")
    ftp.login()
    with tempfile.TemporaryDirectory(prefix="geohealthaccess") as tmpdir:
        # Simple download
        fname = utils.download_from_ftp(ftp, url, tmpdir)
        assert os.path.isfile(fname)
        mtime = os.path.getmtime(fname)
        # Should not be downloaded again
        fname = utils.download_from_ftp(ftp, url, tmpdir)
        assert mtime == os.path.getmtime(fname)
        # Should be because of overwrite
        fname = utils.download_from_ftp(ftp, url, tmpdir, overwrite=True)
        assert mtime != os.path.getmtime(fname)
    ftp.close()


@pytest.mark.remote
def test_size_from_ftp():
    url = (
        "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2020/BDI/"
        "bdi_ppp_2020.tif"
    )
    ftp = FTP("ftp.worldpop.org.uk")
    ftp.login()
    assert utils.size_from_ftp(ftp, url) == 13735590
    ftp.close()


def test_unzip():
    archive = resource_filename(__name__, "data/madagascar.zip")
    expected = resource_filename(__name__, "data/madagascar.geojson")
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        utils.unzip(archive, tmpdir)
        extracted = os.path.join(tmpdir, "madagascar.geojson")
        assert os.path.isfile(extracted)
        assert filecmp.cmp(extracted, expected)
