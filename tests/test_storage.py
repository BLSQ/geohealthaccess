"""Tests for storage module."""

import pytest

from geohealthaccess.storage import Location


@pytest.mark.parametrize(
    "location, protocol, path",
    [
        ("/data/output/cost.tif", "local", "/data/output/cost.tif"),
        ("../input/", "local", "../input/"),
        ("s3://my-bucket/data/cost.tif", "s3", "my-bucket/data/cost.tif"),
        ("gcs://my-bucket/data/input/", "gcs", "my-bucket/data/input/"),
    ],
)
def test_storage_location(location, protocol, path):
    loc = Location(location)
    assert loc.protocol == protocol
    assert loc.path == path
