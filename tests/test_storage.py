"""Tests for storage module.

These tests rely on a local S3-compatible setup such as Minio [1].
Example setup::

    # download minio binary
    wget https://dl.min.io/server/minio/release/darwin-amd64/minio
    chmod +x minio

    # copy test data
    mkdir -p /minio
    cp -r \
        /app/geohealthaccess/tests/data/dji-test-data \
        /minio/dji

    # run local minio server
    ./minio server /tmp/minio

References
----------
.. [1] `<https://github.com/minio/minio>`_
"""

import os
from tempfile import TemporaryDirectory

import pytest
from pkg_resources import resource_filename

from geohealthaccess import storage
from geohealthaccess.storage import Location


@pytest.mark.parametrize(
    "location, protocol, path",
    [
        ("/data/output/cost.tif", "local", "/data/output/cost.tif"),
        ("../input/", "local", "../input/"),
        ("s3://my-bucket/data/cost.tif", "s3", "my-bucket/data/cost.tif"),
        ("gcs://my-bucket/data/input/", "gcs", "my-bucket/data/input/"),
    ],
)
def test_storage_location(location, protocol, path):
    loc = Location(location)
    assert loc.protocol == protocol
    assert loc.path == path


@pytest.fixture
def local_s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "minioadmin")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "")


LOCAL_DIR = resource_filename(__name__, "data/dji-test-data")
S3_DIR = "s3://geohealthaccess-tests/dji"


def test_ls(local_s3):

    local = storage.ls(LOCAL_DIR)
    remote = storage.ls(S3_DIR)
    assert "aoi.wkt" in local and "aoi.wkt" in remote


def test_cp(local_s3):

    # cp to s3
    src = resource_filename(__name__, "data/madagascar.wkt")
    dst = os.path.join(S3_DIR, "test", "madagascar.wkt")
    storage.cp(src, dst)
    assert "madagascar.wkt" in storage.ls(os.path.dirname(dst))

    # cp from s3
    src = dst
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        dst = os.path.join(tmp_dir, "madagascar.wkt")
        storage.cp(src, dst)
        assert "madagascar.wkt" in os.listdir(tmp_dir)


def test_rm(local_s3):

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        src = resource_filename(__name__, "data/madagascar.wkt")
        dst = os.path.join(tmp_dir, "madagascar.wkt")
        storage.cp(src, dst)
        storage.rm(dst)
        assert "madagascar.wkt" not in os.listdir(tmp_dir)

    # cp to s3
    src = resource_filename(__name__, "data/madagascar.wkt")
    dst = os.path.join(S3_DIR, "test", "madagascar.wkt")
    storage.cp(src, dst)
    assert "madagascar.wkt" in storage.ls(os.path.dirname(dst))
    storage.rm(dst)
    assert "madagascar.wkt" not in storage.ls(os.path.dirname(dst))


def test_exists(local_s3):

    local = resource_filename(__name__, "data/madagascar.wkt")
    remote = os.path.join(S3_DIR, "aoi.wkt")
    assert storage.exists(local)
    assert not storage.exists(local + "xxx")
    assert storage.exists(remote)
    assert not storage.exists(remote + "xxx")


def test_size(local_s3):

    local = os.path.join(LOCAL_DIR, "gadm.gpkg")
    remote = os.path.join(S3_DIR, "gadm.gpkg")
    assert storage.size(local) == storage.size(remote) == 147456


def test_glob(local_s3):

    files = storage.glob(S3_DIR + "/input/*.tif")
    assert len(files) == 15
    for f in files:
        assert f.startswith("s3://")
        assert f.endswith(".tif")


def test_open_(local_s3):

    with storage.open_(S3_DIR + "/input/meta.json") as f:
        assert "dji" in f.read()


def test_recursive_download(local_s3):

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        remote_dir = S3_DIR + "/output"
        storage.recursive_download(remote_dir, tmp_dir, show_progress=False)
        fp = os.path.join(tmp_dir, "walk", "cost.tif")
        print([f for f in os.walk(tmp_dir)])
        assert os.path.isfile(fp)
        mtime = os.path.getmtime(fp)
        storage.recursive_download(
            remote_dir, tmp_dir, show_progress=False, overwrite=False
        )
        assert os.path.getmtime(fp) == mtime
        storage.recursive_download(
            remote_dir, tmp_dir, show_progress=False, overwrite=True
        )
        assert os.path.getmtime(fp) != mtime


def test_recursive_upload(local_s3):

    local_dir = os.path.join(LOCAL_DIR, "output")
    remote_dir = S3_DIR + "/test/output"
    fp = remote_dir + "/walk/cost.tif"

    for f in storage.find(remote_dir):
        storage.rm(f)

    storage.recursive_upload(local_dir, remote_dir, show_progress=False)
    assert storage.exists(fp)
    mtime = storage.mtime(fp)
    storage.recursive_upload(
        local_dir, remote_dir, show_progress=False, overwrite=False
    )
    assert storage.mtime(fp) == mtime
