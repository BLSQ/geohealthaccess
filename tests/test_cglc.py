"""Tests for CGLC module."""

import os
import tempfile

from pkg_resources import resource_filename
import pytest
from shapely import wkt

from geohealthaccess.cglc import (
    CGLC,
    tile_id,
    tile_geom,
    parse_filename,
    _is_cglc,
    unique_tiles,
    list_layers,
    find_layer,
)


@pytest.mark.parametrize(
    "url, id_",
    [
        (
            "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/W180N00_ProbaV_LC100_epoch2015_global_v2.0.1_products_EPSG-4326.zip",
            "W180N00",
        ),
        (
            "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/E100N40_ProbaV_LC100_epoch2015_global_v2.0.1_products_EPSG-4326.zip",
            "E100N40",
        ),
        (
            "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/E080N60_ProbaV_LC100_epoch2015_global_v2.0.1_products_EPSG-4326.zip",
            "E080N60",
        ),
    ],
)
def test_tile_id(url, id_):
    assert tile_id(url) == id_


@pytest.mark.parametrize(
    "id_, geom",
    [
        ("W180N00", "POLYGON ((-180 0, -180 -20, -160 -20, -160 0, -180 0))"),
        ("E100N40", "POLYGON ((100 40, 100 20, 120 20, 120 40, 100 40))"),
        ("E080N60", "POLYGON ((80 60, 80 40, 100 40, 100 60, 80 60))"),
    ],
)
def test_tile_geom(id_, geom):
    geom = wkt.loads(geom)
    assert tile_geom(id_).almost_equals(geom, decimal=1)


def test_cglc_parse_manifest():
    manifest = resource_filename(__name__, "data/cglc-manifest-v2.txt")
    manifest = "file://" + manifest
    urls = CGLC.parse_manifest(manifest)
    assert len(urls) == 94
    assert all([url.startswith("https://") for url in urls])


@pytest.mark.remote
def test_cglc_spatial_index():
    cglc = CGLC()
    assert len(cglc.sindex) == 94
    assert cglc.sindex.url.apply(lambda x: x.startswith("https://")).all()
    assert cglc.sindex.is_valid.all()
    assert type(cglc.sindex.index[0]) == str
    assert cglc.sindex.unary_union.bounds == (-180, -60, 180, 80)


@pytest.mark.remote
def test_cglc_search(senegal, madagascar):
    cglc = CGLC()
    assert sorted(cglc.search(senegal)) == ["W020N20"]
    assert sorted(cglc.search(madagascar)) == ["E040N00", "E040S20"]


@pytest.mark.remote
def test_cglc_download():
    cglc = CGLC()
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = cglc.download("W180N40", tmpdir, overwrite=False)
        mtime = os.path.getmtime(fpath)
        assert os.path.isfile(fpath)
        # tile should not be downloaded again
        cglc.download("W180N40", tmpdir, overwrite=False)
        assert os.path.getmtime(fpath) == mtime
        # tile should be downloaded again
        cglc.download("W180N40", tmpdir, overwrite=True)
        assert os.path.getmtime(fpath) != mtime


@pytest.mark.remote
def test_download_size():
    cglc = CGLC()
    assert cglc.download_size("E040N00") == 360011771


def test_parse_filename():
    FNAME = (
        "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1"
        "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    layer = parse_filename(FNAME)
    assert layer.name == "grass-coverfraction-StdDev"
    assert layer.tile == "E040N00"
    assert layer.epoch == 2015
    assert layer.version == "v2.0.1"


def test_parse_filename_errors():
    with pytest.raises(ValueError):
        parse_filename("random_filename.tif")


def test_is_cglc():
    FNAME1 = (
        "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1"
        "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    FNAME2 = (
        "E040N00_ProbaV_LC100_epoch2015" "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    assert _is_cglc(FNAME1)
    assert not _is_cglc(FNAME2)


FNAMES = [
    "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-StdDev_EPSG-4326.tif",
    "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-layer_EPSG-4326.tif",
    "E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-layer_EPSG-4326.tif",
    "E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-StdDev_EPSG-4326.tif",
]


def test_unique_tiles():
    # create temporary dir with empty files named after FNAMES
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        unique = unique_tiles(tmpdir)
        assert len(unique) == 2
        assert "E040N00" in unique and "E040S20" in unique


def test_list_layers():
    # create temporary dir with empty files named after FNAMES
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layernames = list_layers(tmpdir, "E040S20")
        print(layernames)
        assert len(layernames) == 2
        assert "grass-coverfraction-layer" in layernames
        assert "grass-coverfraction-StdDev" in layernames


def test_find_layer():
    # create temporary dir with empty files named after FNAMES
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layerpath = find_layer(tmpdir, "E040S20", "grass-coverfraction-layer")
        assert os.path.isfile(layerpath)
        assert "grass-coverfraction-layer" in os.path.basename(layerpath)
