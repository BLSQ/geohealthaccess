"""Tests for OSM module."""

import os
import tempfile

import geopandas as gpd
import rasterio
import requests
from pkg_resources import resource_filename
import pytest
from rasterio.crs import CRS
from shapely import wkt

from geohealthaccess.osm import (
    Geofabrik,
    _count_objects,
    create_water_raster,
    extract_osm_objects,
    tags_filter,
    thematic_extract,
    to_geojson,
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
        dst_file = os.path.join(tmpdir, "extract.gpkg")
        thematic_extract(osmpbf, theme, dst_file)
        geodf = gpd.read_file(dst_file)
        assert len(geodf) == n_features
        assert geodf.is_valid.all()


def test_extract_osm_objects():
    src_file = resource_filename(__name__, "data/djibouti-200622.osm.pbf")
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        extract_osm_objects(src_file, tmp_dir)
        for theme in ("ferry", "health", "roads", "water"):
            dst_file = os.path.join(tmp_dir, f"{theme}.gpkg")
            data = gpd.read_file(dst_file, driver="GPKG")
            assert not data.empty
            if theme == "highway":
                assert "highway" in data.columns
                assert "surface" in data.columns


def test_create_water_raster():
    src_file = resource_filename(__name__, "data/djibouti-water.gpkg")
    crs = CRS.from_epsg(3857)
    transform = rasterio.Affine(1000, 0, 4647000, 0, -1000, 1427000)
    shape = (203, 187)
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        dst_file = os.path.join(tmp_dir, "water.tif")
        create_water_raster(src_file, dst_file, crs, shape, transform)
        with rasterio.open(dst_file) as src:
            data = src.read(1, masked=True)
            assert data.min() == 0
            assert data.max() == 1
