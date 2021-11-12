"""Tests for storage module.

Notes
-----
These tests rely on a local S3-compatible setup with Minio.

Installation::

    # download minio binary
    wget https://dl.min.io/server/minio/release/darwin-amd64/minio
    chmod +x minio

    # put minio executable somewhere in $PATH
"""

import os
import shutil
import subprocess
from contextlib import contextmanager
from tempfile import TemporaryDirectory

import psutil
import pytest
import s3fs
from pkg_resources import resource_filename

from geohealthaccess import storage


@contextmanager
def minio_serve(data_dir):
    """A Context Manager to launch and close a Minio server."""
    p = subprocess.Popen(["minio", "server", "--address", ":9001", data_dir])
    try:
        yield p
    finally:
        psutil.Process(p.pid).kill()


def _minio_available():
    """Check if Minio command is available."""
    return bool(shutil.which("minio"))


# A decorator to skip tests if minio is not running
minio = pytest.mark.skipif(not _minio_available(), reason="requires minio")


@pytest.fixture
def mock_s3fs(monkeypatch):
    """Mock storage.get_s3fs() to use local Minio server."""

    def mockreturn():
        return s3fs.S3FileSystem(
            key="minioadmin",
            secret="minioadmin",
            client_kwargs={"endpoint_url": "http://localhost:9001", "region_name": ""},
        )

    monkeypatch.setattr(storage, "get_s3fs", mockreturn)


def test_storage_location():

    loc = storage.Location("/data/output/cost.tif")
    assert loc.protocol == "local"
    assert loc.path == "/data/output/cost.tif"

    loc = storage.Location("../input/")
    assert loc.protocol == "local"
    assert loc.path == "../input/"

    loc = storage.Location("s3://bucket/data/cost.tif")
    assert loc.protocol == "s3"
    assert loc.path == "bucket/data/cost.tif"

    loc = storage.Location("gcs://bucket/data/input/")
    assert loc.protocol == "gcs"
    assert loc.path == "bucket/data/input/"


@minio
def test_ls(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):
            ls_local = storage.ls(test_data_dir)
            ls_remote = storage.ls("s3://bucket/input")

    assert sorted(ls_local) == sorted(ls_remote)


@minio
def test_cp(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        os.makedirs(os.path.join(tmp_dir, "bucket2"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            # from local to s3
            src = os.path.join(test_data_dir, "elevation.tif")
            dst = "s3://bucket/input/elevation.tif"
            storage.cp(src, dst)
            assert os.path.isfile(os.path.join(tmp_dir, "bucket/input/elevation.tif"))

            # from s3 to local
            dst2 = os.path.join(tmp_dir, "elevation.tif")
            storage.cp(dst, dst2)
            assert os.path.isfile(dst2)
            assert os.path.getsize(src) == os.path.getsize(dst2)

            # from s3 to s3
            dst3 = "s3://bucket2/elevation.tif"
            storage.cp(dst, dst3)
            assert os.path.isfile(os.path.join(tmp_dir, "bucket2/elevation.tif"))


@minio
def test_rm(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            # local
            src1 = os.path.join(tmp_dir, "bucket/input/elevation.tif")
            storage.rm(src1)
            assert not os.path.isfile(src1)

            # s3
            src2 = "s3://bucket/input/health.gpkg"
            storage.rm(src2)
            assert not os.path.isfile(os.path.join(tmp_dir, "bucket/input/health.gpkg"))


@minio
def test_exists(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            # local
            src1 = os.path.join(test_data_dir, "elevation.tif")
            assert storage.exists(src1)
            assert not storage.exists(src1 + "xxx")

            # s3
            src2 = "s3://bucket/input/elevation.tif"
            assert storage.exists(src2)
            assert not storage.exists(src2 + "xxx")


@minio
def test_size(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            # local
            src1 = os.path.join(test_data_dir, "elevation.tif")
            assert storage.size(src1) == 4365

            # s3
            src2 = "s3://bucket/input/elevation.tif"
            assert storage.size(src2) == 4365


@pytest.mark.skip(reason="issue with timezones")
@minio
def test_mtime(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            src1 = os.path.join(tmp_dir, "bucket/input/elevation.tif")
            src2 = "s3://bucket/input/elevation.tif"
            assert storage.mtime(src1) == storage.mtime(src2) == os.path.getmtime(src1)


@minio
def test_open_(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            with storage.open_(os.path.join(test_data_dir, "meta.json")) as f:
                assert "com" in f.read()

            with storage.open_("s3://bucket/input/meta.json") as f:
                assert "com" in f.read()


@minio
def test_check_sizes(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            src1 = os.path.join(tmp_dir, "bucket/input/elevation.tif")
            src2 = "s3://bucket/input/elevation.tif"
            assert storage._check_sizes(src1, src2)


@pytest.mark.skip(reason="issue with timezones")
@minio
def test_check_mtimes(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/input")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "input"))

        with minio_serve(tmp_dir):

            src1 = os.path.join(tmp_dir, "bucket/input/elevation.tif")
            src2 = "s3://bucket/input/elevation.tif"
            assert not storage._check_mtimes(src1, src2)


def test_no_ending_slash():
    assert storage._no_ending_slash("/data/input/") == "/data/input"
    assert storage._no_ending_slash("/data/input") == "/data/input"


@minio
def test_recursive_download(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))
        test_data_dir = resource_filename(__name__, "data/com-test-data/raw")
        shutil.copytree(test_data_dir, os.path.join(tmp_dir, "bucket", "raw"))

        with minio_serve(tmp_dir):

            src = "s3://bucket/raw"
            dst = os.path.join(tmp_dir, "raw-test")
            storage.recursive_download(src, dst, show_progress=False, overwrite=False)
            fp = os.path.join(dst, "cglc/landcover_Bare.tif")
            assert os.path.isfile(fp)
            mtime = os.path.getmtime(fp)

            # should not be downloaded again
            storage.recursive_download(src, dst, show_progress=False, overwrite=False)
            assert os.path.getmtime(fp) == mtime


@minio
def test_recursive_upload(mock_s3fs):
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        os.makedirs(os.path.join(tmp_dir, "bucket"))

        with minio_serve(tmp_dir):

            src = resource_filename(__name__, "data/com-test-data/raw")
            dst = "s3://bucket/com-raw"
            storage.recursive_upload(src, dst, show_progress=False, overwrite=False)
            fp = os.path.join(tmp_dir, "bucket/com-raw/cglc/landcover_Bare.tif")
            assert os.path.isfile(fp)
            mtime = os.path.getmtime(fp)

            # should not be uploaded again
            storage.recursive_upload(src, dst, show_progress=False, overwrite=False)
            assert os.path.getmtime(fp) == mtime
