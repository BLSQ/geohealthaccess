import os
import tempfile

import pytest
import requests
from pkg_resources import resource_filename

from geohealthaccess import utils

COUNTRIES_URL = "https://github.com/BLSQ/geohealthaccess/raw/master/geohealthaccess/resources/countries.geojson"
SRTM_URL = "https://github.com/BLSQ/geohealthaccess/raw/master/geohealthaccess/resources/srtm.geojson"
FTP_TEST_URL = "ftp://speedtest.tele2.net/1KB.zip"


@pytest.mark.parametrize(
    "size, expected",
    [(1024, "1.0 KB"), (542215845, "542.2 MB"), (845965254785, "846.0 GB")],
)
def test_human_readable_size(size, expected):
    assert utils.human_readable_size(size) == expected


@pytest.mark.http
def test_http_same_size():
    """Ignore error if a new countries.geojson is being pushed."""
    fname = resource_filename("geohealthaccess", "resources/countries.geojson")
    print(fname)
    assert utils.http_same_size(COUNTRIES_URL, fname)
    assert not utils.http_same_size(SRTM_URL, fname)
    with requests.Session() as s:
        assert utils.http_same_size(COUNTRIES_URL, fname, s)


def test_country_geometry():
    mdg = utils.country_geometry("mdg")
    assert mdg.is_valid
    assert not mdg.is_empty
    assert mdg.area == pytest.approx(51.07, 0.01)


@pytest.mark.http
def test_download_from_url():
    with tempfile.TemporaryDirectory() as tmpdir:

        # Test simple download
        fname = utils.download_from_url(
            requests.session(), SRTM_URL, tmpdir, show_progress=False
        )
        assert utils.http_same_size(SRTM_URL, fname)
        mtime = os.path.getmtime(fname)

        # File should not be downloaded again if file sizes are equal
        utils.download_from_url(
            requests.session(), SRTM_URL, tmpdir, show_progress=False
        )
        assert mtime == os.path.getmtime(fname)

        # File should be downloaded again if overwrite=True
        utils.download_from_url(
            requests.session(), SRTM_URL, tmpdir, show_progress=False, overwrite=True
        )
        assert mtime != os.path.getmtime(fname)


@pytest.mark.http
def test_download_from_ftp():
    with tempfile.TemporaryDirectory() as tmpdir:

        # Simple download
        fname = utils.download_from_ftp(FTP_TEST_URL, tmpdir)
        assert os.path.isfile(fname)
        mtime = os.path.getmtime(fname)

        # Should not be downloaded again
        fname = utils.download_from_ftp(FTP_TEST_URL, tmpdir)
        assert mtime == os.path.getmtime(fname)

        # Should be because of overwrite
        fname = utils.download_from_ftp(FTP_TEST_URL, tmpdir, overwrite=True)
        assert mtime != os.path.getmtime(fname)
