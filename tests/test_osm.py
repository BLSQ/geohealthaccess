"""Tests for OSM module."""

import os
import tempfile

import geopandas as gpd
import pytest
from pkg_resources import resource_filename
import requests
from shapely import wkt

from geohealthaccess.osm import (
    _count_objects,
    tags_filter,
    thematic_extract,
    to_geojson,
    Geofabrik,
)


def test_geofabrik_search():
    geo = Geofabrik()
    with open(resource_filename(__name__, "data/madagascar.wkt")) as f:
        geom = wkt.load(f)
    assert "madagascar-latest" in geo.search(geom)
    with open(resource_filename(__name__, "data/senegal.wkt")) as f:
        geom = wkt.load(f)
    assert "senegal-and-gambia" in geo.search(geom)


def test_geofabrik_download(monkeypatch):
    def mockreturn(self, chunk_size):
        return [b"", b"", b""]

    monkeypatch.setattr(requests.Response, "iter_content", mockreturn)

    geo = Geofabrik()
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        fp = geo.download("ben", tmp_dir, show_progress=False, overwrite=False)
        assert os.path.isfile(fp)
        assert os.path.basename(fp) == "benin-latest.osm.pbf"


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
