import pytest
from pkg_resources import resource_filename

from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString
from datetime import datetime
from geohealthaccess import geofabrik


@pytest.fixture(scope="module")
def geofabrik_samples():
    """Sample webpages from Geofabrik parsed with BeautifulSoup."""
    samples = {}
    for page in ("index.html", "africa.html", "kenya.html"):
        with open(resource_filename(__name__, f"data/{page}")) as f:
            samples[page] = BeautifulSoup(f, "html.parser")


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
    "page, expected_header", [
        ("index.html", "OpenStreetMap Data Extracts"),
        ("africa.html", "Other Formats and Auxiliary Files"),
        ("kenya.html", "Other Formats and Auxiliary Files")
    ]
)
def test__header(page, expected_header):
    resource = f"data/{page}"
    with open(resource) as f:
        soup = BeautifulSoup(f, "html.parser")
    table = soup.find("table")
    assert geofabrik._header(table) == expected_header


@pytest.mark.parametrize(
    "page, name", [
        ("index.html", "OpenStreetMap Data Extracts"),
        ("africa.html", "Africa"),
        ("kenya.html", "Kenya")
    ]
)
def test_name(page, name):
    url = resource_to_url(f"data/{page}")
    page = geofabrik.Page(url)
    assert page.name == name


@pytest.mark.parametrize(
    "page, n_rows", [
        ("index.html", 8),
        ("africa.html", 43),
        ("kenya.html", 77)
    ]
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


@pytest.fixture(scope=module)
def sample_regions():
    return geofabrik.Region("africa"), geofabrik.Region("africa/kenya")


@pytest.mark.http
def test_url(sample_regions):
    africa, kenya = sample_regions
    assert africa.url == "http://download.geofabrik.de/africa.html"
    assert kenya.url == "http://download.geofabrik.de/africa/kenya.html"


@pytest.mark.http
def test_files(sample_regions):
    for region in sample_regions:
        assert len(region.files) >= 1
        for f in region.files:
            assert f
            assert isinstance(f, str)


@pytest.mark.http
def test_datasets(sample_regions):
    for region in sample_regions:
        assert len(region.datasets) >= 1
        for dataset in region.datasets:
            assert isinstance(dataset, dict)
            assert isinstance(dataset["date"], datetime)
            assert isinstance(dataset["file"], str)
            assert isinstance(dataset["url"], str)
