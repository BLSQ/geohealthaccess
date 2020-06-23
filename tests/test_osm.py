"""Tests for OSM module."""

import os
import tempfile

import geopandas as gpd
import pytest
from pkg_resources import resource_filename

from geohealthaccess.osm import (
    _count_objects,
    tags_filter,
    thematic_extract,
    to_geojson,
)


def test_count_objects():
    osmpbf = resource_filename(__name__, "data/comores-200622.osm.pbf")
    assert _count_objects(osmpbf) == {"nodes": 489302, "ways": 79360, "relations": 28}


def test_tags_filter():
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        osmpbf = resource_filename(__name__, "data/comores-200622.osm.pbf")
        fpath = tags_filter(
            osmpbf, os.path.join(tmpdir, "comores-highway.osm.pbf"), "w/highway"
        )
        assert _count_objects(fpath) == {"nodes": 62142, "ways": 4298, "relations": 0}


def test_to_geojson():
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        osmpbf = resource_filename(__name__, "data/comores-forests.osm.pbf")
        fpath = to_geojson(osmpbf, os.path.join(tmpdir, "comores-forests.geojson"))
        forests = gpd.read_file(fpath)
        assert len(forests) == 26
        assert forests.is_valid.all()


@pytest.mark.parametrize(
    "theme, n_features", [("roads", 9215), ("health", 51), ("water", 861), ("ferry", 2)]
)
def test_thematic_extract(theme, n_features):
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        osmpbf = resource_filename(__name__, "data/djibouti-200622.osm.pbf")
        extract = thematic_extract(osmpbf, theme, os.path.join(tmpdir, "extract.gpkg"))
        geodf = gpd.read_file(extract)
        assert len(geodf) == n_features
        assert geodf.is_valid.all()
