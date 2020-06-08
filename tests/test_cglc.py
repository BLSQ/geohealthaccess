import os

import pytest
from shapely import wkt
import tempfile

from geohealthaccess import cglc


def test_tile_name():
    URL = "https://s3-eu-west-1.amazonaws.com/vito.landcover.global/2015/E000N40_ProbaV_LC100_epoch2015_global_v2.0.2_products_EPSG-4326.zip"
    assert cglc.tile_name(URL) == "E000N40"


@pytest.mark.parametrize(
    "name, expected_geom",
    [
        ("E000N00", "POLYGON ((0.0 0.0, 0.0 -20.0, 20.0 -20.0, 20.0 0.0, 0.0 0.0))"),
        (
            "W080S40",
            "POLYGON ((-80.0 -40.0, -80.0 -60.0, -60.0 -60.0, -60.0 -40.0, -80.0 -40.0))",
        ),
        (
            "E160N80",
            "POLYGON ((160.0 80.0, 160.0 60.0, 180.0 60.0, 180.0 80.0, 160.0 80.0))",
        ),
    ],
)
def test_to_geom(name, expected_geom):
    geom = cglc.to_geom(name)
    expected_geom = wkt.loads(expected_geom)
    assert geom.almost_equals(expected_geom, decimal=1)


def test_build_tiles_index():
    tilename = "E160N80"
    expected_geom = wkt.loads(
        "POLYGON ((160.0 80.0, 160.0 60.0, 180.0 60.0, 180.0 80.0, 160.0 80.0))"
    )
    tiles = cglc.build_tiles_index()
    url = tiles.loc[tilename].url
    geom = tiles.loc[tilename].geometry
    assert url.startswith("https://")
    assert url.endswith(".zip")
    assert geom.almost_equals(expected_geom, decimal=1)


def test_required_tiles():
    # This is a simplified polygon of Madagascar
    MDG_SIMPLIFIED = """MULTIPOLYGON (
        ((49.84 -17.07, 49.86 -16.92, 50.02 -16.69, 49.96 -16.86, 49.84 -17.07)),
        ((48.32 -13.25, 48.37 -13.40, 48.22 -13.39, 48.19 -13.26, 48.32 -13.25)),
        ((49.35 -12.09, 50.48 -15.44, 47.13 -24.93, 45.15 -25.60, 43.22 -22.25,
        43.93 -17.48, 49.35 -12.09)))"""
    geom = wkt.loads(MDG_SIMPLIFIED)
    tiles = cglc.required_tiles(geom)
    assert len(tiles) == 2
    for url in tiles:
        assert url.startswith("https://")
        assert url.endswith(".zip")


# List of files for Madagascar
LISTDIR = [
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_shrub-coverfraction-StdDev_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_moss-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_DataDensityIndicator_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_moss-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_water-permanent-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_tree-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_bare-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_discrete-classification-proba_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_discrete-classification_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_tree-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_snow-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_tree-coverfraction-StdDev_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_discrete-classification-proba_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_water-seasonal-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_water-seasonal-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_forest-type-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_discrete-classification_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_moss-coverfraction-StdDev_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_water-permanent-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_DataDensityIndicator_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_bare-coverfraction-StdDev_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_forest-type-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_urban-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_shrub-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_snow-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_bare-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_crops-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_grass-coverfraction-StdDev_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_urban-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_bare-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_shrub-coverfraction-StdDev_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_tree-coverfraction-layer_EPSG-4326.tif',
    'E040N00_ProbaV_LC100_epoch2015_global_v2.0.1_moss-coverfraction-layer_EPSG-4326.tif',
    'E040S20_ProbaV_LC100_epoch2015_global_v2.0.1_shrub-coverfraction-layer_EPSG-4326.tif'
]


def _touch(filename):
    """Create empty file."""
    open(filename, "a").close()


def test__available_files():
    TILE_NAME = "E040S20"
    # Create temp dir with empty files from LISTDIR
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in LISTDIR:
            open(os.path.join(tmpdir, f), "a").close()
        available_files = cglc._available_files(TILE_NAME, tmpdir)
    assert len(available_files) == 14


def test_coverfraction_layers():
    # Create temp dir with empty files from LISTDIR
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in LISTDIR:
            open(os.path.join(tmpdir, f), "a").close()
        layers = cglc.coverfraction_layers(tmpdir)
    assert len(layers) == 32
