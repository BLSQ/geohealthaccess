"""Tests for Geofabrik module."""

import os
import tempfile
from datetime import datetime
from random import randint

import geopandas as gpd
import pytest
import requests
from pkg_resources import resource_filename
from requests_file import FileAdapter

from geohealthaccess.geofabrik import Page, Region, SpatialIndex


@pytest.fixture
def africa_page():
    """Local URL to africa.html."""
    fpath = resource_filename(__name__, "data/africa.html")
    return "file://" + fpath


@pytest.fixture
def kenya_page():
    """Local URL to kenya.html."""
    fpath = resource_filename(__name__, "data/kenya.html")
    return "file://" + fpath


@pytest.fixture
def index_page():
    """Local URL to index.html."""
    fpath = resource_filename(__name__, "data/index.html")
    return "file://" + fpath


def test_page_parsing(index_page, africa_page, kenya_page):
    # Geofabrik index page
    with requests.Session() as s:
        s.mount("file://", FileAdapter())
        index = Page(s, index_page)
        assert index.name == "OpenStreetMap Data Extracts"
        assert index.raw_details is None
        assert index.subregions is None
        assert len(index.continents) == 8
        # Geofabrik Africa page
        africa = Page(s, africa_page)
        assert africa.name == "Africa"
        assert len(africa.raw_details) == 43
        assert len(africa.subregions) == 55
        assert africa.continents is None
        # Geofabrik Kenya page
        kenya = Page(s, kenya_page)
        assert kenya.name == "Kenya"
        assert len(kenya.raw_details) == 77
        assert kenya.subregions is None
        assert kenya.continents is None


@pytest.fixture(scope="module")
def africa():
    with requests.Session() as s:
        return Region(s, "africa")


@pytest.fixture(scope="module")
def kenya():
    with requests.Session() as s:
        return Region(s, "africa/kenya")


@pytest.mark.remote
def test_region_url(africa, kenya):
    assert africa.url == "http://download.geofabrik.de/africa.html"
    assert kenya.url == "http://download.geofabrik.de/africa/kenya.html"


@pytest.mark.remote
def test_region_files(africa, kenya):
    MIN_EXPECTED_FILES = 10
    assert len(africa.files) >= MIN_EXPECTED_FILES
    assert len(kenya.files) >= MIN_EXPECTED_FILES
    # check access to random file from the list
    for files in (africa.files, kenya.files):
        r = requests.head(africa.BASE_URL + files[randint(0, len(files) - 1)])
        assert r.status_code == 200


@pytest.mark.remote
def test_region_datasets(africa, kenya):
    MIN_EXPECTED_DATASETS = 10
    assert len(kenya.datasets) >= MIN_EXPECTED_DATASETS
    assert len(africa.datasets) >= MIN_EXPECTED_DATASETS
    for dataset in kenya.datasets + africa.datasets:
        assert isinstance(dataset["date"], datetime)
        assert isinstance(dataset["file"], str)
        assert isinstance(dataset["url"], str)


@pytest.mark.remote
def test_region_latest(africa, kenya):
    for latest in (africa.latest, kenya.latest):
        assert latest.startswith("http://download.geofabrik.de")
        assert latest.endswith(".osm.pbf")


@pytest.mark.remote
def test_region_subregions(africa, kenya):
    assert len(africa.subregions) >= 50
    assert "/africa/kenya" in africa.subregions
    assert kenya.subregions is None


@pytest.mark.remote
def test_region_get_geometry(africa, kenya):
    assert africa.get_geometry().bounds == pytest.approx((-27, -60, 67, 38), abs=1)
    assert kenya.get_geometry().bounds == pytest.approx((34, -5, 42, 5), abs=1)


@pytest.mark.remote
def test_spatial_index_build():
    oceania = SpatialIndex()
    oceania.CONTINENTS = ["australia-oceania"]
    oceania.build()
    assert "Tonga" in oceania.sindex.name.values
    assert oceania.sindex.is_valid.all()


@pytest.fixture(scope="module")
def africa_sindex():
    sindex = gpd.read_file(resource_filename(__name__, "data/geofabrik-africa.gpkg"))
    sindex.set_index(["id"], drop=True, inplace=True)
    return sindex


def test_spatial_index_cache_get(africa_sindex):
    africa = SpatialIndex()
    africa.BASE_URL = None
    africa.sindex = africa_sindex
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        africa.cache_path = os.path.join(tmpdir, "cache.gpkg")
        africa.cache()
        assert os.path.isfile(africa.cache_path)
        assert africa.sindex.is_valid.all()
        africa.get()
        assert africa.sindex.is_valid.all()


def test_spatial_index_search(senegal, madagascar, africa_sindex):
    africa = SpatialIndex()
    africa.sindex = africa_sindex
    # senegal
    region_id, match = africa.search(senegal)
    assert region_id == "/africa/senegal-and-gambia"
    assert match == pytest.approx(0.62, abs=0.01)
    # madagascar
    region_id, match = africa.search(madagascar)
    assert region_id == "/africa/madagascar"
    assert match == pytest.approx(0.64, abs=0.01)


@pytest.mark.remote
def test_download(africa_sindex):
    africa = SpatialIndex()
    africa.sindex = africa_sindex
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        osm_pbf = africa.download("africa/djibouti", tmpdir)
        mtime = os.path.getmtime(osm_pbf)
        assert os.path.isfile(osm_pbf)
        # should not be downloaded again
        africa.download("africa/djibouti", tmpdir, overwrite=False)
        assert os.path.getmtime(osm_pbf) == mtime
        # should be downloaded again
        africa.download("africa/djibouti", tmpdir, overwrite=True)
        assert os.path.getmtime(osm_pbf) != mtime
