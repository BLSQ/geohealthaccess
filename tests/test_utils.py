"""Tests for utils module."""

import filecmp
import os
import tempfile
from ftplib import FTP

import pytest
import requests
from requests_file import FileAdapter

from geohealthaccess import utils


@pytest.mark.parametrize(
    "size, expected",
    [(1024, "1.0 KB"), (542215845, "542.2 MB"), (845965254785, "846.0 GB")],
)
def test_human_readable_size(size, expected):
    assert utils.human_readable_size(size) == expected


def test_size_from_url(tests_data):
    """Local URL."""
    url = tests_data["madagascar.geojson"]["local_url"]
    with requests.Session() as s:
        s.mount("file://", FileAdapter())
        assert utils.size_from_url(s, url) == 22498


@pytest.mark.http
def test_size_from_url_http(tests_data):
    """Remote URL."""
    url = tests_data["madagascar.geojson"]["github_url"]
    with requests.Session() as s:
        s.mount("file://", FileAdapter())
        assert utils.size_from_url(s, url) == 22498


def test_http_same_size(tests_data):
    """Use a local URL to avoid network calls."""
    url = tests_data["madagascar.geojson"]["local_url"]
    path = tests_data["madagascar.geojson"]["local_path"]
    with requests.Session() as s:
        s.mount("file://", FileAdapter())
        assert utils.http_same_size(s, url, path)


def test_country_geometry():
    mdg = utils.country_geometry("mdg")
    assert mdg.is_valid
    assert not mdg.is_empty
    assert mdg.area == pytest.approx(51.07, 0.01)


def test_download_from_url(tests_data):
    """Use a local URL to avoid network calls."""
    url = tests_data["madagascar.geojson"]["local_url"]
    with tempfile.TemporaryDirectory(
        prefix="geohealthaccess_"
    ) as tmpdir, requests.Session() as s:
        s.mount("file://", FileAdapter())
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


@pytest.mark.http
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


@pytest.mark.http
def test_size_from_ftp():
    url = (
        "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2020/BDI/"
        "bdi_ppp_2020.tif"
    )
    ftp = FTP("ftp.worldpop.org.uk")
    ftp.login()
    assert utils.size_from_ftp(ftp, url) == 13735590
    ftp.close()


def test_unzip(tests_data):
    archive = tests_data["madagascar.zip"]["local_path"]
    reference = tests_data["madagascar.geojson"]["local_path"]
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        utils.unzip(archive, tmpdir)
        extracted = os.path.join(tmpdir, "madagascar.geojson")
        assert os.path.isfile(extracted)
        assert filecmp.cmp(extracted, reference)
