"""Tests for preprocessing module."""


from geohealthaccess.preprocessing import reproject
import pytest
from pkg_resources import resource_filename
import os
from tempfile import TemporaryDirectory
import rasterio
from rasterio import Affine
from rasterio.crs import CRS
from geohealthaccess import preprocessing


def test_default_compression_int():
    for dtype in ("int", "int8", "int16", "uint8", "uint16"):
        options = preprocessing.default_compression(dtype)
        assert options.get("compress") == "deflate"
        assert options.get("predictor") == 2
        assert options.get("zlevel") == 6
        assert options.get("num_threads") == "all_cpus"


def test_default_compression_float():
    for dtype in ("float", "float32", "float64"):
        options = preprocessing.default_compression(dtype)
        assert options.get("compress") == "deflate"
        assert options.get("predictor") == 3
        assert options.get("zlevel") == 6
        assert options.get("num_threads") == "all_cpus"


def test_create_grid(senegal):
    transform, shape, bounds = preprocessing.create_grid(
        senegal, dst_crs=CRS.from_epsg(3857), dst_res=100
    )
    assert transform.a == 100
    assert shape == (5019, 6844)
    xmin, ymin, xmax, ymax = bounds
    assert xmin == pytest.approx(-1952098)
    assert ymin == pytest.approx(1380553)
    assert xmax == pytest.approx(-1267706)
    assert ymax == pytest.approx(1882328)


def test_merge_tiles():
    tiles = [
        resource_filename(__name__, f"data/{tile_id}.tif")
        for tile_id in ("S03E030", "S04E029", "S04E030")
    ]
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        mosaic = preprocessing.merge_tiles(
            tiles, os.path.join(tmpdir, "mosaic.tif"), nodata=-9999
        )
        with rasterio.open(mosaic) as src:
            assert src.height == 720
            assert src.width == 720
            assert src.nodata == -9999
            assert src.profile.get("dtype") == "int16"
            assert src.profile.get("tiled")
            assert src.profile.get("compress") == "deflate"


def test_reproject():
    bounds = (
        3226806.0262841275,
        -497360.4695224336,
        3432420.99829369,
        -256444.80445172396,
    )
    src_file = resource_filename(__name__, "data/S03E030.tif")
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        dst_file = preprocessing.reproject(
            src_file,
            dst_raster=os.path.join(tmpdir, "raster.tif"),
            dst_crs=CRS.from_epsg(3857),
            dst_bounds=bounds,
            dst_res=1000,
        )
        with rasterio.open(dst_file) as src:
            assert src.width == 207
            assert src.height == 242
            assert src.profile.get("compress") == "deflate"
            assert src.profile.get("tiled")


def test_concatenate_bands():
    pass
