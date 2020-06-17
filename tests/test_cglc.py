import os
import tempfile

import geopandas as gpd
import pytest
from pkg_resources import resource_filename
from shapely import wkt

from geohealthaccess import cglc


def resource_to_url(resource):
    """Get file:// url corresponding to a given pkg resource."""
    fname = resource_filename(__name__, resource)
    return f"file://{fname}"


@pytest.fixture(scope="module")
def tile():
    """Return an initialized CGLC Tile."""
    return cglc.Tile(
        "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/"
        "E000N20_ProbaV_LC100_epoch2015_global_v2.0.1_products_EPSG-4326.zip"
    )


@pytest.fixture(scope="module")
def catalog():
    """Return a CGLC Catalog initialized with a local manifest file."""
    return cglc.Catalog(resource_to_url("data/cglc-manifest.txt"))


def test_tile_id(tile):
    assert tile.id_ == "E000N20"


def test_tile_geom(tile):
    assert tile.geom == wkt.loads("POLYGON ((0 20, 0 0, 20 0, 20 20, 0 20))")


@pytest.mark.http
def test_tile_download():
    tile = cglc.Tile(
        "https://s3-eu-west-1.amazonaws.com/vito.landcover.global/2015/"
        "W180N40_ProbaV_LC100_epoch2015_global_v2.0.2_products_EPSG-4326.zip"
    )
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        fname = tile.download(tmpdir, show_progress=False, overwrite=False)
        mtime = os.path.getmtime(fname)
        assert os.path.isfile(fname)

        # tile should not be downloaded again
        tile.download(tmpdir, show_progress=False, overwrite=False)
        assert os.path.getmtime(fname) == mtime

        # tile should be downloaded again
        tile.download(tmpdir, show_progress=False, overwrite=True)
        assert os.path.getmtime(fname) != mtime


def test_parse_manifest(catalog):
    tiles = catalog.parse_manifest(catalog.url)
    assert len(tiles) == 94
    for tile in tiles:
        assert isinstance(tile, cglc.Tile)
        assert tile.url
        assert tile.id_
        assert tile.geom


def test_parse_build(catalog):
    sindex = catalog.build()
    assert isinstance(sindex, gpd.GeoDataFrame)
    assert len(sindex) == 94
    assert sindex.index[0] == "E000N00"
    assert sindex.is_valid.all()


def test_search(catalog, senegal):
    tiles = catalog.search(senegal)
    assert len(tiles) == 1
    assert tiles[0].id_ == "W020N20"


def test_parse_filename():
    FNAME = (
        "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1"
        "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    layer = cglc.parse_filename(FNAME)
    assert layer.name == "grass-coverfraction-StdDev"
    assert layer.tile == "E040N00"
    assert layer.epoch == 2015
    assert layer.version == "v2.0.1"


def test_is_cglc():
    FNAME1 = (
        "E040N00_ProbaV_LC100_epoch2015_global_v2.0.1"
        "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    FNAME2 = (
        "E040N00_ProbaV_LC100_epoch2015"
        "_grass-coverfraction-StdDev_EPSG-4326.tif"
    )
    assert cglc._is_cglc(FNAME1)
    assert not cglc._is_cglc(FNAME2)


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
        unique = cglc.unique_tiles(tmpdir)
        assert len(unique) == 2
        assert "E040N00" in unique and "E040S20" in unique


def test_list_layers():
    # create temporary dir with empty files named after FNAMES
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layernames = cglc.list_layers(tmpdir, "E040S20")
        print(layernames)
        assert len(layernames) == 2
        assert "grass-coverfraction-layer" in layernames
        assert "grass-coverfraction-StdDev" in layernames


def test_find_layer():
    # create temporary dir with empty files named after FNAMES
    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        for fname in FNAMES:
            open(os.path.join(tmpdir, fname), "a").close()
        layerpath = cglc.find_layer(tmpdir, "E040S20", "grass-coverfraction-layer")
        assert os.path.isfile(layerpath)
        assert "grass-coverfraction-layer" in os.path.basename(layerpath)
