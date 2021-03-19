"""Tests for cglc module."""

import os
from glob import glob
from tempfile import TemporaryDirectory

import numpy as np
import pytest
import rasterio
import requests
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely import wkt

from geohealthaccess import cglc


@pytest.fixture(scope="module")
def catalog():
    return cglc.CGLC()


def test_download_url(catalog):
    url = catalog.download_url("E000N00", "BuiltUp", 2019)
    assert url == (
        "https://s3-eu-west-1.amazonaws.com/vito.landcover.global/v3.0.1/2019/E000N00/"
        "E000N00_PROBAV_LC100_global_v3.0.1_2019-nrt_"
        "BuiltUp-CoverFraction-layer_EPSG-4326.tif"
    )

    with pytest.raises(ValueError):
        catalog.download_url("E000N00", "NotALabel", 2019)

    with pytest.raises(ValueError):
        catalog.download_url("E000N00", "BuiltUp", 2000)


def test_format_latlon(catalog):
    assert catalog.format_latlon(20, 30) == "E030N20"
    assert catalog.format_latlon(-40, -120) == "W120S40"


def test_search(catalog):
    with open(resource_filename(__name__, "data/madagascar.wkt")) as f:
        geom = wkt.load(f)
        tiles = sorted(catalog.search(geom))
        expected = sorted(["E040N00", "E040S20"])
        assert tiles == expected
    with open(resource_filename(__name__, "data/senegal.wkt")) as f:
        geom = wkt.load(f)
        tiles = sorted(catalog.search(geom))
        expected = sorted(["W020N20"])
        assert tiles == expected


def test_download(catalog, monkeypatch):
    tile = "W020N20"

    # mock requests iter_content method so that file content
    # is not downloaded.
    # nb: a header request is still sent.
    def mockreturn(self, chunk_size):
        return [b"", b"", b""]

    monkeypatch.setattr(requests.Response, "iter_content", mockreturn)

    with TemporaryDirectory() as tmpdir:
        f = catalog.download(
            tile=tile,
            label="BuiltUp",
            output_dir=tmpdir,
            year=2019,
            show_progress=False,
        )
        f = os.path.basename(f)
        assert f.startswith(tile) and f.endswith(".tif")
        assert "BuiltUp" in f and "2019" in f


def test_download_all(catalog, monkeypatch):
    tile = "W020N20"

    # mock requests iter_content method so that file content
    # is not downloaded.
    # nb: a header request is still sent.
    def mockreturn(self, chunk_size):
        return [b"", b"", b""]

    monkeypatch.setattr(requests.Response, "iter_content", mockreturn)

    with TemporaryDirectory() as tmpdir:
        catalog.download_all(
            tile=tile,
            output_dir=tmpdir,
            year=2019,
            show_progress=False,
        )
        for label in catalog.LABELS:
            assert glob(os.path.join(tmpdir, f"*{label}*.tif"))


def test_preprocess(catalog):
    # use geometry from D.R. Congo
    with open(resource_filename(__name__, "data/cod.wkt")) as f:
        geom = wkt.load(f)
    with TemporaryDirectory() as tmpdir:
        # reproject to 10km pixel sizes for faster processing
        cglc.preprocess(
            input_dir=os.path.join(resource_filename(__name__, "data/cglc")),
            dst_dir=tmpdir,
            geom=geom,
            crs=CRS.from_epsg(3857),
            res=10000,
            overwrite=False,
        )
        for label in catalog.LABELS:
            # check that raster exists
            ls = glob(os.path.join(tmpdir, f"*{label}*.tif"))
            assert ls
            with rasterio.open(ls[0]) as src:
                # check raster metadata
                assert src.crs == CRS.from_epsg(3857)
                assert src.nodata == -9999
                assert src.dtypes[0] == "float32"
                data = src.read(1, masked=True)
                # values should be between 0 and 100 as they are percentages
                assert data.min() >= 0
                assert data.max() <= 100
                # at least 25% of non-null pixels
                h, w = data.shape
                assert np.count_nonzero(data) / (h * w) >= 0.25
