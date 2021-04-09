"""Tests for CLI."""

import os
from tempfile import TemporaryDirectory
from glob import glob
from pkg_resources import resource_filename
import requests

import pytest
from click.testing import CliRunner

from geohealthaccess.cli import cli


def _minio_is_running():
    """Check that a Minio instance is running."""
    try:
        requests.get("http://localhost:9000")
        return True
    except requests.ConnectionError:
        return False


# marker to skip tests if minio is not running
minio = pytest.mark.skipif(not _minio_is_running(), reason="requires minio")


def _credentials_set():
    """Check that EarthData credentials are set."""
    user = bool(os.environ.get("EARTHDATA_USERNAME"))
    pswd = bool(os.environ.get("EARTHDATA_PASSWORD"))
    return user and pswd


# marker to skip tests if earthdata credentials are not set
earthdata = pytest.mark.skipif(
    not _credentials_set(), reason="requires earthdata credentials"
)


@pytest.mark.web
@pytest.mark.slow
@earthdata
def test_download():
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["download", "--country", "com", "--output-dir", tmp_dir]
        )
        assert result.exit_code == 0
        assert glob(os.path.join(tmp_dir, "cglc", "landcover_*.tif"))
        assert glob(os.path.join(tmp_dir, "gsw", "seasonality*.tif"))
        assert glob(os.path.join(tmp_dir, "osm", "*.osm.pbf"))
        assert glob(os.path.join(tmp_dir, "srtm", "*.hgt.zip"))
        assert glob(os.path.join(tmp_dir, "worldpop", "*ppp*.tif"))


@pytest.mark.slow
def test_preprocess():
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        runner = CliRunner()
        input_dir = resource_filename(__name__, "data/com-test-data/raw")
        result = runner.invoke(
            cli, ["preprocess", "-c", "com", "-i", input_dir, "-o", tmp_dir, "-r", 1000]
        )
        assert result.exit_code == 0
        assert len(glob(os.path.join(tmp_dir, "landcover_*.tif"))) == 10
        assert "elevation.tif" in os.listdir(tmp_dir)
        assert "health.gpkg" in os.listdir(tmp_dir)
        assert "meta.json" in os.listdir(tmp_dir)
        assert "population.tif" in os.listdir(tmp_dir)
        assert "roads.gpkg" in os.listdir(tmp_dir)
        assert "water.gpkg" in os.listdir(tmp_dir)
        assert "water_gsw.tif" in os.listdir(tmp_dir)
        assert "water_osm.tif" in os.listdir(tmp_dir)


@pytest.mark.slow
def test_access():
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        runner = CliRunner()
        input_dir = resource_filename(__name__, "data/com-test-data/input")
        result = runner.invoke(
            cli,
            [
                "access",
                "-c",
                "com",
                "-i",
                input_dir,
                "-o",
                tmp_dir,
                "--areas",
                resource_filename(__name__, "data/com-test-data/gadm.gpkg"),
                "--car",
                "--walk",
                "--no-bike",
            ],
        )
        assert result.exit_code == 0
        assert "cost.tif" in os.listdir(os.path.join(tmp_dir, "health", "car"))
        assert "areas.gpkg" in os.listdir(os.path.join(tmp_dir, "health", "car"))
        assert "areas.csv" in os.listdir(os.path.join(tmp_dir, "health", "car"))
        assert "cost.tif" in os.listdir(os.path.join(tmp_dir, "health", "walk"))
        assert "areas.gpkg" in os.listdir(os.path.join(tmp_dir, "health", "walk"))
        assert "areas.csv" in os.listdir(os.path.join(tmp_dir, "health", "walk"))
