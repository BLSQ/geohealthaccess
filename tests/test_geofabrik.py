"""Tests for geofabrik.py module."""

import os
import tempfile
from datetime import datetime

import geopandas as gpd
import pytest
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag
from pkg_resources import resource_filename

from geohealthaccess import geofabrik


def resource_to_url(resource):
    """Get file:// url corresponding to a given pkg resource."""
    fname = resource_filename(__name__, resource)
    return f"file://{fname}"


@pytest.mark.parametrize(
    "page_id, name, n_details, n_subregions, n_special, n_continents",
    [
        ("index", "OpenStreetMap Data Extracts", 0, 0, 0, 8),
        ("kenya", "Kenya", 77, 0, 0, 0),
        ("africa", "Africa", 43, 55, 1, 0),
    ],
)
def test_page(page_id, name, n_details, n_subregions, n_special, n_continents):
    url = "file://" + resource_filename(__name__, f"data/{page_id}.html")
    page = geofabrik.Page(url)
    assert page.name == name

    for attribute, expected in zip(
        [page.raw_details, page.subregions, page.special_subregions, page.continents],
        [n_details, n_subregions, n_special, n_continents],
    ):
        if expected > 0:
            assert len(attribute) == expected
        else:
            assert not attribute


@pytest.mark.parametrize(
    "page, expected_header",
    [
        ("index.html", "OpenStreetMap Data Extracts"),
        ("africa.html", "Other Formats and Auxiliary Files"),
        ("kenya.html", "Other Formats and Auxiliary Files"),
    ],
)
def test__header(page, expected_header):
    html = resource_filename(__name__, f"data/{page}")
    with open(html) as f:
        soup = BeautifulSoup(f, "html.parser")
    table = soup.find("table")
    assert geofabrik._header(table) == expected_header


@pytest.mark.parametrize(
    "page, name",
    [
        ("index.html", "OpenStreetMap Data Extracts"),
        ("africa.html", "Africa"),
        ("kenya.html", "Kenya"),
    ],
)
def test_name(page, name):
    url = resource_to_url(f"data/{page}")
    page = geofabrik.Page(url)
    assert page.name == name


@pytest.mark.parametrize(
    "page, n_rows", [("index.html", 8), ("africa.html", 43), ("kenya.html", 77)]
)
def test__parse_table(page, n_rows):
    url = resource_to_url(f"data/{page}")
    page = geofabrik.Page(url)
    first_table = page.soup.find("table")
    dataset = page._parse_table(first_table)
    assert len(dataset) == n_rows
    for element in dataset:
        for _, item in element.items():
            assert isinstance(item, Tag) or isinstance(item, NavigableString)


@pytest.mark.parametrize(
    "page, n_details, n_subregions, n_special, n_continents",
    [
        ("index.html", 0, 0, 0, 8),
        ("kenya.html", 77, 0, 0, 0),
        ("africa.html", 43, 55, 1, 0),
    ],
)
def test_parse_tables(page, n_details, n_subregions, n_special, n_continents):
    url = resource_to_url(f"data/{page}")
    page = geofabrik.Page(url)
    for attribute, expected in zip(
        [page.raw_details, page.subregions, page.special_subregions, page.continents],
        [n_details, n_subregions, n_special, n_continents],
    ):
        if expected > 0:
            assert len(attribute) == expected
        else:
            assert not attribute


def test_url(sample_geofabrik_regions):
    africa, kenya = sample_geofabrik_regions
    assert africa.url == "http://download.geofabrik.de/africa.html"
    assert kenya.url == "http://download.geofabrik.de/africa/kenya.html"


def test_files(sample_geofabrik_regions):
    N_FILES = {"africa": 43, "africa/kenya": 77}
    for region in sample_geofabrik_regions:
        assert len(region.files) == N_FILES[region.id]
        for f in region.files:
            assert f
            assert isinstance(f, str)


def test_datasets(sample_geofabrik_regions):
    N_DATASETS = {"africa": 16, "africa/kenya": 15}
    for region in sample_geofabrik_regions:
        assert len(region.datasets) == N_DATASETS[region.id]
        for dataset in region.datasets:
            assert isinstance(dataset, dict)
            assert isinstance(dataset["date"], datetime)
            assert isinstance(dataset["file"], str)
            assert isinstance(dataset["url"], str)


def test_latest(sample_geofabrik_regions):
    LATEST = {"africa": "africa-200609.osm.pbf", "africa/kenya": "kenya-200609.osm.pbf"}
    for region in sample_geofabrik_regions:
        assert region.latest.split("/")[-1] == LATEST[region.id]


def test_subregions(sample_geofabrik_regions):
    africa, kenya = sample_geofabrik_regions
    assert len(africa.subregions) == 55
    assert kenya.subregions is None


@pytest.mark.http
def test_build_spatial_index():
    idx_expected = gpd.read_file(
        resource_filename(__name__, "data/idx_oceania.geojson")
    )
    idx_expected = idx_expected.set_index(["id"], drop=True)
    idx = geofabrik.build_spatial_index(include="australia and oceania")
    assert idx.equals(idx_expected)


def test__cover(senegal, index_africa):
    sen_and_gambia = index_africa.loc["/africa/senegal-and-gambia"].geometry
    ivory_coast = index_africa.loc["/africa/ivory-coast"].geometry
    assert geofabrik._cover(senegal, sen_and_gambia) == pytest.approx(0.61, 0.01)
    assert geofabrik._cover(senegal, ivory_coast) == 0.00


def test_find_best_region(senegal, index_africa):
    region_id, cover = geofabrik.find_best_region(index_africa, senegal)
    assert region_id == "/africa/senegal-and-gambia"
    assert cover == pytest.approx(0.61, 0.01)


@pytest.mark.http
def test_download_latest_data():
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        osm_pbf = geofabrik.download_latest_data("/africa/comores", tmpdir)
        mtime = os.path.getmtime(osm_pbf)
        assert os.path.isfile(osm_pbf)

        # should not be downloaded again
        geofabrik.download_latest_data("/africa/comores", tmpdir)
        assert os.path.getmtime(osm_pbf) == mtime

        # should be downloaded again
        geofabrik.download_latest_data("/africa/comores", tmpdir, overwrite=True)
        assert os.path.getmtime(osm_pbf) != mtime


@pytest.mark.parametrize(
    "expression, n_objects",
    [
        ("w/highway", {"nodes": 62142, "ways": 4298, "relations": 0}),
        ("w/highway=residential", {"nodes": 25291, "ways": 3065, "relations": 0}),
        ("nwr/natural=water nwr/waterbank", {"nodes": 323, "ways": 17, "relations": 1}),
    ],
)
def test_tags_filter(expression, n_objects):
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        comores = resource_filename(__name__, "data/comores.osm.pbf")
        fname = geofabrik.tags_filter(
            comores, os.path.join(tmpdir, "filtered.osm.pbf"), expression
        )
        assert geofabrik.count_osm_objects(fname) == n_objects


def test_to_geojson():
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        comores = resource_filename(__name__, "data/comores-water.osm.pbf")
        fname = os.path.join(tmpdir, "comores-water.geojson")
        geofabrik.to_geojson(comores, fname)
        water = gpd.read_file(fname)
        count = water.geom_type.groupby(water.geom_type).count()
        assert count.LineString == 94
        assert count.MultiPolygon == 16
        assert count.Point == 10


@pytest.mark.parametrize(
    "theme, n_features", [("roads", 4298), ("water", 110), ("health", 66)]
)
def test_thematic_extract(theme, n_features):
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        comores = resource_filename(__name__, "data/comores.osm.pbf")
        fname = os.path.join(tmpdir, f"comores-{theme}.gpkg")
        geofabrik.thematic_extract(comores, theme, fname)
        geodf = gpd.read_file(fname)
        assert len(geodf) == n_features
