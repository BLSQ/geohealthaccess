"""Tests for Geofabrik module."""

import os
from datetime import datetime
from tempfile import TemporaryDirectory

import pytest
import vcr

from geohealthaccess.geofabrik import Geofabrik, Page, Region

BASEURL = "http://download.geofabrik.de/"


@vcr.use_cassette("tests/cassettes/geofabrik-index.yaml")
def test_page_parsing_index():
    url = BASEURL + "index.html"
    page = Page(url)
    assert page.name == "OpenStreetMap Data Extracts"
    assert len(page.continents) == 8


@vcr.use_cassette("tests/cassettes/geofabrik-africa.yaml")
def test_page_parsing_continent():
    url = BASEURL + "africa.html"
    page = Page(url)
    assert page.name == "Africa"
    assert len(page.raw_details) == 37
    assert len(page.subregions) == 55
    assert len(page.special_subregions) == 1


@vcr.use_cassette("tests/cassettes/geofabrik-kenya.yaml")
def test_page_parsing_country():
    url = BASEURL + "africa/kenya.html"
    page = Page(url)
    assert page.name == "Kenya"
    assert len(page.raw_details) == 73


@vcr.use_cassette("tests/cassettes/geofabrik-comores.yaml")
def test_region():
    region = Region("/africa/comores")
    assert region.id == "africa/comores"
    assert region.level == 1
    assert region.name == "Comores"
    assert region.extent.is_valid
    assert region.url == "http://download.geofabrik.de/africa/comores.html"


@vcr.use_cassette("tests/cassettes/geofabrik-comores.yaml")
def test_region_files():
    region = Region("/africa/comores")
    assert len(region.files) == 65
    assert "/africa/comores-latest.osm.pbf" in region.files


@vcr.use_cassette("tests/cassettes/geofabrik-comores.yaml")
def test_region_datasets():
    region = Region("africa/comores")
    assert len(region.datasets) == 12
    assert isinstance(region.datasets[0]["date"], datetime)
    assert isinstance(region.datasets[0]["file"], str)
    assert isinstance(region.datasets[0]["url"], str)
    assert region.datasets[0]["url"].startswith("http://")
    assert region.datasets[0]["file"].endswith(".osm.pbf")


@vcr.use_cassette("tests/cassettes/geofabrik-comores.yaml")
def test_region_latest():
    region = Region("africa/comores")
    assert region.latest.endswith(".osm.pbf")


@vcr.use_cassette("tests/cassettes/geofabrik-france.yaml")
def test_region_subregions():
    region = Region("europe/france")
    assert len(region.subregions) == 27
    assert "/europe/france/alsace" in region.subregions


def test_geofabrik_sindex():
    geofab = Geofabrik()
    assert len(geofab.sindex) == 363
    row = geofab.sindex.loc["africa"]
    assert row.name == "africa"
    assert row.geometry.is_valid


def test_geofabrik_search(senegal):
    geofab = Geofabrik()
    region_id, match = geofab.search(senegal)
    assert region_id == "africa/senegal-and-gambia"
    assert match == pytest.approx(0.62, rel=0.01)


@vcr.use_cassette("tests/cassettes/geofabrik-saotomeprincipe-download.yaml")
def test_geofabrik_download():
    geofabrik = Geofabrik()
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        osmpbf = geofabrik.download("africa/sao-tome-and-principe", tmpdir)
        mtime = os.path.getmtime(osmpbf)
        assert os.path.isfile(osmpbf)
        # should not download again (overwrite=False)
        geofabrik.download("africa/sao-tome-and-principe", tmpdir, overwrite=False)
        assert os.path.getmtime(osmpbf) == mtime
        # should download again (overwrite=True)
        geofabrik.download("africa/sao-tome-and-principe", tmpdir, overwrite=True)
        assert os.path.getmtime(osmpbf) != mtime
