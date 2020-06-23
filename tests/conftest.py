"""Configuration and fixtures for Pytest."""

import os

import pytest
from pkg_resources import resource_filename
from shapely import wkt


def pytest_addoption(parser):
    """Add --remote pytest option."""
    parser.addoption(
        "--remote",
        action="store_true",
        default=False,
        help="run tests requesting remote data",
    )


def pytest_configure(config):
    """Add `remote` pytest marker."""
    config.addinivalue_line("markers", "remote: mark test as requesting remote data")


def pytest_collection_modifyitems(config, items):
    """Configure `remote` pytest marker."""
    if config.getoption("--remote"):
        return
    skip_remote = pytest.mark.skip(reason="need --remote option to run")
    for item in items:
        if "remote" in item.keywords:
            item.add_marker(skip_remote)


@pytest.fixture
def tests_data(scope="session"):
    """A dict with paths and URLs to tests data files."""
    datafiles = {}
    tests_dataurl = "https://github.com/BLSQ/geohealthaccess/raw/master/tests/data/"
    tests_datadir = os.path.dirname(
        resource_filename(__name__, "data/madagascar.geojson")
    )
    for f in os.listdir(tests_datadir):
        datafiles[f] = {}
        datafiles[f]["github_url"] = tests_dataurl + f
        datafiles[f]["local_path"] = os.path.join(tests_datadir, f)
        datafiles[f]["local_url"] = "file://" + datafiles[f]["local_path"]
    return datafiles


@pytest.fixture
def senegal(scope="module"):
    """Load a simplified geometry of Senegal."""
    fname = resource_filename(__name__, "data/senegal.wkt")
    with open(fname) as f:
        return wkt.load(f)


@pytest.fixture
def madagascar(scope="module"):
    """Load a simplified geometry of Madagascar."""
    fname = resource_filename(__name__, "data/madagascar.wkt")
    with open(fname) as f:
        return wkt.load(f)
