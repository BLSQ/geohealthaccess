"""Tests for geohealthaccess module."""

import os
import shutil
from tempfile import TemporaryDirectory

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from pkg_resources import resource_filename
from shapely import wkt

from geohealthaccess.geohealthaccess import GeoHealthAccess


def test_gha_init():

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        GeoHealthAccess(
            raw_dir=os.path.join(tmp_dir, "raw"),
            input_dir=os.path.join(tmp_dir, "input"),
            output_dir=os.path.join(tmp_dir, "output"),
            country="dji",
            crs="epsg:3857",
            resolution=500,
        )


@pytest.fixture(scope="module")
def djibouti(tmp_path_factory):
    """A GeoHealthAccess instance."""
    tmp_dir = tmp_path_factory.mktemp("data")
    with open(resource_filename(__name__, "data/dji-test-data/aoi.wkt")) as f:
        aoi = wkt.load(f)
    gha = GeoHealthAccess(
        raw_dir=tmp_dir.joinpath("raw").as_posix(),
        input_dir=tmp_dir.joinpath("input").as_posix(),
        output_dir=tmp_dir.joinpath("output").as_posix(),
        country="dji",
        area_of_interest=aoi,
        resolution=1000,
    )
    yield gha
    shutil.rmtree(str(tmp_dir))


def test_gha_dump_update_spatial_info(djibouti):

    djibouti.dump_spatial_info()

    crs = djibouti.crs
    transform = djibouti.transform
    shape = djibouti.shape
    area = djibouti.area_of_interest
    bounds = djibouti.bounds

    djibouti.update_spatial_info()

    # update should lead to same values
    assert crs == djibouti.crs
    assert transform == djibouti.transform
    assert shape == djibouti.shape
    assert area == djibouti.area_of_interest
    assert bounds == djibouti.bounds


def test_compute_mask(djibouti):

    mask = djibouti.compute_mask()
    assert mask.shape == djibouti.shape
    assert np.count_nonzero(mask) == pytest.approx(5100, abs=100)


@pytest.mark.slow
def test_preprocessing(djibouti):

    djibouti.raw_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "raw"
    )

    djibouti.preprocessing(show_progress=None)

    assert "elevation.tif" in os.listdir(djibouti.input_dir)
    assert "health.gpkg" in os.listdir(djibouti.input_dir)
    assert "landcover_Bare.tif" in os.listdir(djibouti.input_dir)
    assert "meta.json" in os.listdir(djibouti.input_dir)
    assert "roads.gpkg" in os.listdir(djibouti.input_dir)
    assert "slope.tif" in os.listdir(djibouti.input_dir)
    assert "water.gpkg" in os.listdir(djibouti.input_dir)
    assert "water_gsw.tif" in os.listdir(djibouti.input_dir)
    assert "water_osm.tif" in os.listdir(djibouti.input_dir)

    # all rasters should be aligned, except population
    for f in os.listdir(djibouti.input_dir):
        if f.endswith(".tif") and "population" not in f:
            with rasterio.open(os.path.join(djibouti.input_dir, f)) as src:
                assert src.height == djibouti.shape[0]
                assert src.width == djibouti.shape[1]
                assert src.crs == djibouti.crs
                assert src.transform == djibouti.transform


def test_moving_obstacle(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    obstacle = djibouti.moving_obstacle(max_slope=10)
    assert obstacle.shape == djibouti.shape
    assert np.count_nonzero(obstacle)
    assert np.count_nonzero(~obstacle)


def test_off_road_speed(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    off_road = djibouti.off_road_speed()
    assert off_road.shape == djibouti.shape
    # mean off road speed should be between 2 and 5 km/h
    mean_speed = off_road[off_road > 0].mean()
    assert mean_speed >= 2
    assert mean_speed <= 5


def test_on_road_speed(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    on_road = djibouti.on_road_speed()
    assert on_road.shape == djibouti.shape
    # mean off road speed should be between 10 and 70 km/h
    mean_speed = on_road[on_road > 0].mean()
    assert mean_speed >= 10
    assert mean_speed <= 70


def test_segment_speed(djibouti):

    residential = djibouti.moving_speeds["transport"]["highway"]["residential"]
    unpaved = djibouti.moving_speeds["transport"]["surface"]["dirt"]
    assert djibouti.segment_speed("residential") == residential
    assert djibouti.segment_speed("residential", surface="unpaved") == pytest.approx(
        residential * unpaved
    )


def test_friction_surface(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    f_car = djibouti.friction_surface(mode="car", max_slope=35)
    f_walk = djibouti.friction_surface(mode="walk", max_slope=35, walk_speed=5)

    assert f_car.shape == djibouti.shape
    assert f_walk.shape == djibouti.shape
    assert not (f_car == f_walk).all()


def test_health_facilities(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    health = djibouti.health_facilities()
    assert len(health) >= 25
    assert health.crs == djibouti.crs
    assert health.is_valid.all()


def test_isotropic_costdistance(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    djibouti.isotropic_costdistance(
        src_friction=djibouti.friction_surface(mode="car", max_slope=35),
        src_target=djibouti.health_facilities(),
        dst_dir=os.path.join(djibouti.output_dir, "test-car"),
    )

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-car", "cost.tif")
    ) as src:
        assert src.transform == djibouti.transform
        data = src.read(1, masked=True)
        # mean travel time should be between 30mn and 3h
        assert data.mean() >= 1800
        assert data.mean() <= 10800

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-car", "nearest.tif")
    ) as src:
        assert src.transform == djibouti.transform

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-car", "backlink.tif")
    ) as src:
        assert src.transform == djibouti.transform


def test_anisotropic_costdistance(djibouti):

    djibouti.input_dir = os.path.join(
        resource_filename(__name__, "data/dji-test-data"), "input"
    )

    djibouti.anisotropic_costdistance(
        src_friction=djibouti.friction_surface(mode="walk", max_slope=35),
        src_target=djibouti.health_facilities(),
        dst_dir=os.path.join(djibouti.output_dir, "test-walk"),
    )

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-walk", "cost.tif")
    ) as src:
        assert src.transform == djibouti.transform
        data = src.read(1, masked=True)
        # mean travel time should be between 30mn and 10h
        assert data.mean() >= 1800
        assert data.mean() <= 36000

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-walk", "nearest.tif")
    ) as src:
        assert src.transform == djibouti.transform

    with rasterio.open(
        os.path.join(djibouti.output_dir, "test-walk", "backlink.tif")
    ) as src:
        assert src.transform == djibouti.transform


def test_fill(djibouti):

    with rasterio.open(
        resource_filename(__name__, "data/dji-test-data/output/car/cost.tif")
    ) as src:
        nodata = src.nodata
        cost = src.read(1)

    filled = djibouti.fill(cost, nodata)
    assert np.count_nonzero(cost == nodata) > np.count_nonzero(filled == nodata)


def test_population_counts(djibouti):

    areas = gpd.read_file(
        resource_filename(__name__, "data/dji-test-data/gadm.gpkg"), driver="GPKG"
    )
    counts = djibouti.population_counts(areas)
    assert counts.iloc[0] == pytest.approx(115000, rel=0.1)
    assert counts.iloc[1] == pytest.approx(41000, rel=0.1)
    assert counts.iloc[2] == pytest.approx(538000, rel=0.1)


def test_accessibility_stats(djibouti):

    areas = gpd.read_file(
        resource_filename(__name__, "data/dji-test-data/gadm.gpkg"), driver="GPKG"
    )

    with rasterio.open(
        resource_filename(__name__, "data/dji-test-data/output/car/cost.tif")
    ) as src:
        stats = djibouti.accessibility_stats(
            cost=src.read(1, masked=True), areas=areas, levels=[30, 90]
        )

    assert stats[30][0] == pytest.approx(80000, rel=0.1)
    assert stats[90][1] == pytest.approx(33000, rel=0.1)
