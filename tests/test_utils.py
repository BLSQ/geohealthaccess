"""Tests for utils module."""

import filecmp
import os
import tempfile

import pytest
from pkg_resources import resource_filename

from geohealthaccess import utils

GITHUB = "https://raw.githubusercontent.com/BLSQ/geohealthaccess/master/"


@pytest.mark.parametrize(
    "size, expected",
    [(1024, "1.0 KB"), (542215845, "542.2 MB"), (845965254785, "846.0 GB")],
)
def test_human_readable_size(size, expected):
    assert utils.human_readable_size(size) == expected


def test_country_geometry():
    mdg = utils.country_geometry("mdg")
    assert mdg.is_valid
    assert not mdg.is_empty
    assert mdg.area == pytest.approx(51.07, 0.01)


def test_country_geometry_notfound():
    with pytest.raises(ValueError):
        utils.country_geometry("not_a_country")


def test_unzip():
    archive = resource_filename(__name__, "data/madagascar.zip")
    expected = resource_filename(__name__, "data/madagascar.geojson")
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        utils.unzip(archive, tmpdir)
        extracted = os.path.join(tmpdir, "madagascar.geojson")
        assert os.path.isfile(extracted)
        assert filecmp.cmp(extracted, expected)
