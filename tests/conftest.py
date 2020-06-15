"""Configuration and fixtures for Pytest."""

import geopandas as gpd
import pytest
from pkg_resources import resource_filename
from shapely import wkt

from geohealthaccess import geofabrik


def pytest_addoption(parser):
    """Add --http pytest option."""
    parser.addoption(
        "--http",
        action="store_true",
        default=False,
        help="run tests making http/ftp requests",
    )


def pytest_configure(config):
    """Add http pytest marker."""
    config.addinivalue_line("markers", "http: mark test as making an http request")


def pytest_collection_modifyitems(config, items):
    """Configure http pytest marker."""
    if config.getoption("--http"):
        return
    skip_http = pytest.mark.skip(reason="need --http option to run")
    for item in items:
        if "http" in item.keywords:
            item.add_marker(skip_http)


@pytest.fixture
def senegal(scope="module"):
    """Load a simplified geometry of Senegal."""
    fname = resource_filename(__name__, "data/senegal.wkt")
    with open(fname) as f:
        return wkt.load(f)


def resource_to_url(resource):
    """Get file:// url corresponding to a given pkg resource."""
    fname = resource_filename(__name__, resource)
    return f"file://{fname}"


@pytest.fixture(scope="module")
def sample_geofabrik_regions():
    """Parse local Geofabrik webpages of Africa and Kenya."""
    africa = geofabrik.Region("africa", parse=False)
    africa_url = resource_to_url("data/africa.html")
    africa.page = geofabrik.Page(africa_url)
    africa.name = africa.page.name
    kenya = geofabrik.Region("africa/kenya", parse=False)
    kenya_url = resource_to_url("data/kenya.html")
    kenya.page = geofabrik.Page(kenya_url)
    kenya.name = kenya.page.name
    return africa, kenya


@pytest.fixture(scope="module")
def index_africa():
    """Load Geofabrik spatial index limited to Africa."""
    fname = resource_filename(__name__, "data/geofabrik_africa.gpkg")
    idx = gpd.read_file(fname)
    idx = idx.set_index(["id"], drop=True)
    return idx
