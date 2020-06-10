import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--http",
        action="store_true",
        default=False,
        help="run tests making http/ftp requests",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "http: mark test as making an http request")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--http"):
        return
    skip_http = pytest.mark.skip(reason="need --http option to run")
    for item in items:
        if "http" in item.keywords:
            item.add_marker(skip_http)
