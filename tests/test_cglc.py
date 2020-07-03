import os
from tempfile import TemporaryDirectory

import pytest
import vcr

from geohealthaccess.cglc import (
    CGLC,
    _is_cglc,
    find_layer,
    list_layers,
    parse_filename,
    unique_tiles,
)


@vcr.use_cassette("tests/cassettes/cglc-manifest.yaml")
def test_parse_manifest():
    cglc = CGLC()
    assert len(cglc.manifest) == 94
    assert all([url.startswith("https://") for url in cglc.manifest])


@vcr.use_cassette("tests/cassettes/cglc-manifest.yaml")
def test_spatial_index():
    cglc = CGLC()
    assert len(cglc.sindex) == 94
    assert type(cglc.sindex.index[0]) == str
    assert cglc.sindex.unary_union.bounds == (-180, -60, 180, 80)


@vcr.use_cassette("tests/cassettes/cglc-manifest.yaml")
def test_cglc_search(senegal, madagascar):
    cglc = CGLC()
    assert sorted(cglc.search(senegal)) == ["W020N20"]
    assert sorted(cglc.search(madagascar)) == ["E040N00", "E040S20"]


@vcr.use_cassette("tests/cassettes/cglc-W180N40.yaml")
def test_cglc_download():
    cglc = CGLC()
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        fpath = cglc.download("W180N40", tmpdir, overwrite=False)
        mtime = os.path.getmtime(fpath)
        assert os.path.isfile(fpath)
        # tile should not be downloaded again
        cglc.download("W180N40", tmpdir, overwrite=False)
        assert os.path.getmtime(fpath) == mtime
        # tile should be downloaded again
        cglc.download("W180N40", tmpdir, overwrite=True)
        assert os.path.getmtime(fpath) != mtime


@vcr.use_cassette("tests/cassettes/cglc-W180N40-head.yaml")
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
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        unique = unique_tiles(tmpdir)
        assert len(unique) == 2
        assert "E040N00" in unique and "E040S20" in unique


def test_list_layers():
    # create temporary dir with empty files named after FNAMES
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layernames = list_layers(tmpdir, "E040S20")
        print(layernames)
        assert len(layernames) == 2
        assert "grass-coverfraction-layer" in layernames
        assert "grass-coverfraction-StdDev" in layernames


def test_find_layer():
    # create temporary dir with empty files named after FNAMES
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layerpath = find_layer(tmpdir, "E040S20", "grass-coverfraction-layer")
        assert os.path.isfile(layerpath)
        assert "grass-coverfraction-layer" in os.path.basename(layerpath)
