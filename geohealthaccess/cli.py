"""GeoHealthAccess command-line interface.

Examples
--------
Getting help::

    geohealthaccess --help

Getting help for a specific subcommand::

    geohealthaccess download --help
    geohealthaccess preprocess --help
    geohealthaccess access --help
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import click
import rasterio
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely.geometry import shape

from geohealthaccess.cglc import CGLC, unique_tiles
from geohealthaccess.data import Intermediary, Raw
from geohealthaccess.errors import MissingDataError
from geohealthaccess.geofabrik import SpatialIndex
from geohealthaccess.gsw import GSW
from geohealthaccess.modeling import (
    anisotropic_costdistance,
    combine_speed,
    compute_friction,
    isotropic_costdistance,
    rasterize_destinations,
    seconds_to_minutes,
    speed_from_landcover,
    speed_from_roads,
    travel_obstacles,
)
from geohealthaccess.osm import thematic_extract, create_water_raster
from geohealthaccess.preprocessing import (
    compute_aspect,
    compute_slope,
    concatenate_bands,
    create_grid,
    mask_raster,
    merge_tiles,
    reproject,
)
from geohealthaccess.srtm import SRTM
from geohealthaccess.utils import country_geometry, unzip
from geohealthaccess.worldpop import WorldPop

log = logging.getLogger(__name__)


@click.group()
def cli():
    """Map accessibility to health services."""
    pass


@cli.command()
@click.option("--country", "-c", required=True, type=str, help="ISO A3 country code")
@click.option("--output-dir", "-o", type=click.Path(), help="Output directory")
@click.option(
    "--earthdata-user",
    "-u",
    required=True,
    envvar="EARTHDATA_USERNAME",
    type=str,
    help="NASA EarthData username",
)
@click.option(
    "--earthdata-pass",
    "-p",
    required=True,
    envvar="EARTHDATA_PASSWORD",
    type=str,
    help="NASA EarthData password",
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def download(country, output_dir, earthdata_user, earthdata_pass, overwrite):
    """Download input datasets."""
    geom = country_geometry(country)

    # Set data directories automatically if they are not provided
    if not output_dir:
        output_dir = os.path.join(os.curdir, "Data", "Input")

    # Create data directories
    NAMES = ("Population", "Land_Cover", "OpenStreetMap", "Surface_Water", "Elevation")
    datadirs = [os.path.join(output_dir, name) for name in NAMES]
    for datadir in datadirs:
        os.makedirs(datadir, exist_ok=True)

    # Population
    wp = WorldPop()
    wp.login()
    wp.download(country, os.path.join(output_dir, NAMES[0]), overwrite=overwrite)
    wp.logout()

    # Land Cover
    cglc = CGLC()
    tiles = cglc.search(geom)
    for tile in tiles:
        cglc.download(tile, os.path.join(output_dir, NAMES[1]), overwrite=overwrite)

    # OpenStreetMap
    geofab = SpatialIndex()
    geofab.get()
    region_id, _ = geofab.search(geom)
    geofab.download(region_id, os.path.join(output_dir, NAMES[2]), overwrite=overwrite)

    # Global Surface WaterTrue
    gsw = GSW()
    tiles = gsw.search(geom)
    for tile in tiles:
        gsw.download(
            tile, "seasonality", os.path.join(output_dir, NAMES[3]), overwrite=overwrite
        )

    # Digital elevation model
    srtm = SRTM()
    srtm.authentify(earthdata_user, earthdata_pass)
    tiles = srtm.search(geom)
    dst_dir = os.path.join(output_dir, NAMES[4])
    with ThreadPoolExecutor(max_workers=10) as e:
        for i, tile in enumerate(tiles):
            e.submit(
                srtm.download, tile, dst_dir, True, overwrite, i,
            )


@cli.command()
@click.option("--country", "-c", type=str, required=True, help="ISO A3 country code")
@click.option(
    "--crs", "-s", type=str, required=True, help="CRS as a PROJ4 string",
)
@click.option(
    "--resolution", "-r", type=float, default=100, help="Pixel size in `crs` units"
)
@click.option("--input-dir", "-i", type=click.Path(), help="Input data directory")
@click.option(
    "--output-dir", "-o", type=click.Path(), help="Output data directory",
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def preprocess(input_dir, output_dir, crs, resolution, country, overwrite):
    """Preprocess and co-register input datasets."""
    # Set data directories if not provided and create them if necessary
    if not input_dir:
        input_dir = os.path.join(os.curdir, "Data", "Input")
    if not output_dir:
        output_dir = os.path.join(os.curdir, "Data", "Intermediary")
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    for p in (input_dir, output_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Create raster grid from CLI options
    geom = country_geometry(country)
    dst_crs = CRS.from_string(crs)
    transform, shape, bounds = create_grid(geom, dst_crs, resolution)
    args = {
        "dst_crs": dst_crs,
        "dst_bounds": bounds,
        "dst_res": resolution,
        "overwrite": overwrite,
        "geom": geom,
    }

    raw = Raw(input_dir)
    preprocess_land_cover(
        src_files=raw.land_cover,
        dst_raster=output_dir.joinpath("land_cover.tif"),
        **args,
    )
    preprocess_elevation(src_files=raw.elevation, dst_dir=output_dir, **args)
    preprocess_osm(
        src_file=raw.openstreetmap[0],
        dst_dir=output_dir,
        dst_crs=dst_crs,
        dst_shape=shape,
        dst_transform=transform,
        geom=geom,
        overwrite=overwrite,
    )
    preprocess_surface_water(
        src_files=raw.surface_water,
        dst_raster=output_dir.joinpath("surface_water.tif"),
        **args,
    )

    log.info("Writing area of interest to disk.")
    with open(output_dir.joinpath("area_of_interest.geojson"), "w") as f:
        json.dump(geom.__geo_interface__, f)


def preprocess_land_cover(
    src_files, dst_raster, dst_crs, dst_bounds, dst_res, geom=None, overwrite=False
):
    """Preprocess land cover input data.

    Raw .zip CGLC tiles are extracted and mosaicked if necessary. They are
    reprojected according to the specified parameters and individual rasters
    (one per land cover class) are concatenated into a single multi-band raster.

    Parameters
    ----------
    src_files : list of str
        Paths to input .zip CGLC tiles.
    dst_raster : str
        Path to output multi-band raster.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_bounds : tuple of float
        Target raster extent (xmin, ymin, xmax, ymax).
    dst_res : int or float
        Target spatial resolution in `dst_crs` units.
    geom : shapely geometry, optional
        Area of interest (EPSG:4326).
    overwrite : bool, optional
        Overwrite existing files.
    """
    if os.path.isfile(dst_raster) and not overwrite:
        log.info("Land cover data already preprocessed. Skipping.")
        return
    log.info("Starting preprocessing of land cover data.")
    LC_CLASSES = [
        "bare",
        "crops",
        "grass",
        "moss",
        "shrub",
        "tree",
        "urban",
        "water-permanent",
        "water-seasonal",
    ]
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        tmpdir = Path(tmpdir)
        for tile in src_files:
            unzip(tile, tmpdir)

        reprojected_files = []
        tile_names = unique_tiles(tmpdir)
        for tile_name, lc_class in product(tile_names, LC_CLASSES):
            tiles = list(
                tmpdir.glob(f"{tile_name}*{lc_class}-coverfraction-layer*.tif")
            )
            if len(tiles) > 1:
                src_file = merge_tiles(tiles, tmpdir.joinpath("mosaic.tif"), nodata=255)
            else:
                src_file = tiles[0]
            reprojected_files.append(
                reproject(
                    src_raster=src_file,
                    dst_raster=tmpdir.joinpath(f"{lc_class}.tif"),
                    dst_crs=dst_crs,
                    dst_bounds=dst_bounds,
                    dst_res=dst_res,
                    src_nodata=255,
                    dst_nodata=255,
                    dst_dtype="Byte",
                    resampling_method="cubic",
                    overwrite=overwrite,
                )
            )

        if len(reprojected_files) > 1:
            stack = concatenate_bands(
                src_files=reprojected_files,
                dst_file=dst_raster,
                band_descriptions=LC_CLASSES,
            )

        if geom:
            mask_raster(stack, geom)


def preprocess_osm(
    src_file, dst_dir, dst_crs, dst_shape, dst_transform, geom=None, overwrite=False
):
    """Preprocess input OSM data.

    Parameters
    ----------
    src_file : str
        Path to source .osm.pbf file.
    dst_dir : str
        Path to output directory.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_shape : tuple of int
        Output raster shape (height, width).
    dst_transform : Affine
        Output raster transform.
    geom : shapely geometry, optional
        Area of interest (EPSG:4326).
    overwrite : bool, optional
        Overwrite existing files.
    """
    log.info("Starting preprocessing of OSM data.")
    for theme in ("roads", "health", "water", "ferry"):
        dst_file = os.path.join(dst_dir, f"{theme}.gpkg")
        if os.path.isfile(dst_file) and not overwrite:
            log.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
            continue
        try:
            thematic_extract(src_file, theme, dst_file)
        except MissingDataError:
            log.warning(
                f"Skipping extraction of `{theme}` objects due to missing data."
            )
    osm_water = os.path.join(dst_dir, "water.gpkg")
    dst_file = os.path.join(dst_dir, "water_osm.tif")
    create_water_raster(
        osm_water,
        dst_file,
        dst_crs,
        dst_shape,
        dst_transform,
        include_streams=False,
        geom=geom,
        overwrite=overwrite,
    )
    if geom:
        mask_raster(dst_file, geom)


def preprocess_surface_water(
    src_files, dst_raster, dst_crs, dst_bounds, dst_res, geom=None, overwrite=False
):
    """Preprocess input surface water data.

    Parameters
    ----------
    src_files : list of str
        Paths to input .zip GSW tiles.
    dst_raster : str
        Path to output raster.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_bounds : tuple of float
        Target raster extent (xmin, ymin, xmax, ymax).
    dst_res : int or float
        Target spatial resolution in `dst_crs` units.
    geom : shapely geometry, optional
        Area of interest (EPSG:4326).
    overwrite : bool, optional
        Overwrite existing files.
    """
    if os.path.isfile(dst_raster) and not overwrite:
        log.info(f"{os.path.basename(dst_raster)} already exists. Skipping.")
        return
    log.info("Starting preprocessing of surface water data.")
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        if len(src_files) > 1:
            src_file = merge_tiles(
                src_files, os.path.join(tmpdir, "mosaic.tif"), nodata=255
            )

        else:
            src_file = src_files[0]
        dst_raster = reproject(
            src_raster=src_file,
            dst_raster=dst_raster,
            dst_crs=dst_crs,
            dst_bounds=dst_bounds,
            dst_res=dst_res,
            src_nodata=255,
            dst_nodata=255,
            dst_dtype="Byte",
            resampling_method="max",
            overwrite=overwrite,
        )
        if geom:
            mask_raster(dst_raster, geom)


def preprocess_elevation(
    src_files, dst_dir, dst_crs, dst_bounds, dst_res, geom=None, overwrite=False
):
    """Preprocess input elevation data.

    Creates elevation, slope and aspect rasters from SRTM tiles.

    Parameters
    ----------
    src_files : list of str
        Paths to input .zip CGLC tiles.
    dst_dir : str
        Path to output directory.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_bounds : tuple of float
        Target raster extent (xmin, ymin, xmax, ymax).
    dst_res : int or float
        Target spatial resolution in `dst_crs` units.
    geom : shapely geometry, optional
        Area of interest (EPSG:4326).
    overwrite : bool, optional
        Overwrite existing files.
    """
    log.info("Starting preprocessing of elevation data.")
    dst_dem = os.path.join(dst_dir, "elevation.tif")
    dst_slope = os.path.join(dst_dir, "slope.tif")
    dst_aspect = os.path.join(dst_dir, "aspect.tif")
    all_exists = all([os.path.isfile(f) for f in (dst_dem, dst_slope, dst_aspect)])
    if all_exists and not overwrite:
        log.info("All topograpy rasters already exists. Skipping processing.")
        return

    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        # unzip all tiles in a temporary directory
        tmpdir = Path(tmpdir)
        for tile in src_files:
            unzip(tile, tmpdir)

        # merge tiles into a single mosaic if necessary
        tiles = [f.as_posix() for f in tmpdir.glob("*.hgt")]
        if len(tiles) > 1:
            dem = merge_tiles(tiles, tmpdir.joinpath("mosaic.tif"), nodata=-32768)
        else:
            dem = tiles[0]

        # compute slope and aspect before reprojection
        if not os.path.isfile(dst_slope) or overwrite:
            slope = compute_slope(
                dem, tmpdir.joinpath("slope.tif"), percent=False, scale=111120
            )
        else:
            log.info("Slope raster already exists. Skipping processing.")
            slope = dst_slope
        if not os.path.isfile(dst_aspect) or overwrite:
            aspect = compute_aspect(
                dem, tmpdir.joinpath("aspect.tif"), trigonometric=True
            )
        else:
            log.info("Aspect raster already exists. Skipping processing.")
            aspect = dst_aspect

        for src, dst in zip((dem, slope, aspect), (dst_dem, dst_slope, dst_aspect)):

            if os.path.isfile(dst) and not overwrite:
                log.info(
                    f"{os.path.basename(dst)} already exists. Skipping processing."
                )
                continue

            # dtype is Int16 for elevation, and Float32 for slope & aspect
            nodata = -9999
            dtype = "Float32"
            if "elevation" in dst:
                nodata = -32768
                dtype = "Int16"

            dst = reproject(
                src_raster=src,
                dst_raster=dst,
                dst_crs=dst_crs,
                dst_bounds=dst_bounds,
                dst_res=dst_res,
                src_nodata=nodata,
                dst_nodata=nodata,
                dst_dtype=dtype,
                resampling_method="cubic",
                overwrite=overwrite,
            )
            if geom:
                mask_raster(dst, geom)


@cli.command()
@click.option("--input-dir", "-i", type=click.Path(), help="Input data directory")
@click.option("--output-dir", "-o", type=click.Path(), help="Output data directory")
@click.option("--car/--no-car", default=True, help="Enable/disable car scenario")
@click.option("--walk/--no-walk", default=False, help="Enable/disable walk scenario")
@click.option("--bike/--no-bike", default=False, help="Enable/disable bike scenario")
@click.option(
    "--travel-speeds",
    "-s",
    type=click.Path(),
    help="JSON file with custom travel speeds",
)
@click.option(
    "--destinations",
    "-d",
    type=click.Path(),
    multiple=True,
    help="Destination points (GeoJSON or Geopackage)",
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def access(
    input_dir, output_dir, car, walk, bike, travel_speeds, destinations, overwrite
):
    """Map travel times to the provided health facilities."""
    # Set data directories if not provided and create them if necessary
    if not input_dir:
        input_dir = Path(os.path.join(os.curdir, "Data", "Intermediary"))
    if not output_dir:
        output_dir = Path(os.path.join(os.curdir, "Data", "Output"))
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    for p in (input_dir, output_dir):
        p.mkdir(parents=True, exist_ok=True)
    data = Intermediary(input_dir)

    with open(input_dir.joinpath("area_of_interest.geojson")) as f:
        aoi = shape(json.load(f))

    # Use default travel speeds if JSON file is not provided
    if not travel_speeds:
        travel_speeds = resource_filename(__name__, "resources/travel-speeds.json")
    with open(travel_speeds) as f:
        travel_speeds = json.load(f)

    # Speed rasters
    with rasterio.open(data.land_cover) as src:
        dst_transform = src.transform
        dst_crs = src.crs
        dst_width = src.width
        dst_height = src.height
    obstacles = travel_obstacles(
        src_water=(data.surface_water, data.osm_water_raster),
        src_slope=data.slope,
        dst_file=input_dir.joinpath("obstacle.tif"),
        max_slope=25,
        overwrite=overwrite,
    )
    landcover_speed = speed_from_landcover(
        data.land_cover,
        dst_file=input_dir.joinpath("landcover_speed.tif"),
        speeds=travel_speeds["land-cover"],
        overwrite=overwrite,
    )
    transport_speed = speed_from_roads(
        data.roads,
        dst_file=input_dir.joinpath("transport_speed.tif"),
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_width=dst_width,
        dst_height=dst_height,
        src_ferry=data.ferry,
        speeds=travel_speeds["transport"],
        overwrite=overwrite,
    )

    for mode in ("car", "walk"):

        # Skip if disabled in cli options
        if mode == "car" and not car:
            continue
        if mode == "walk" and not walk:
            continue

        # Compute speed and friction rasters
        speed = combine_speed(
            landcover_speed,
            transport_speed,
            obstacles,
            dst_file=input_dir.joinpath(f"speed_{mode}.tif"),
            mode=mode,
        )

        friction = compute_friction(
            speed,
            dst_file=input_dir.joinpath(f"friction_{mode}.tif"),
            max_time=3600,
            one_meter=mode == "walk",
        )
        mask_raster(friction, aoi)

    if not destinations:
        destinations = [data.health]

    for features in destinations:

        basename = os.path.basename(features)
        name, ext = os.path.splitext(basename)
        dst_file = input_dir.joinpath(f"{name}.tif")
        dest_raster = rasterize_destinations(
            features,
            dst_file,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_height=dst_height,
            dst_width=dst_width,
            overwrite=overwrite,
        )
        mask_raster(dest_raster, aoi)

        if car:
            isotropic_costdistance(
                src_friction=input_dir.joinpath("friction_car.tif"),
                src_target=dest_raster,
                dst_cost=output_dir.joinpath(f"cost_car_{name}.tif"),
                dst_nearest=output_dir.joinpath(f"nearest_car_{name}.tif"),
                dst_backlink=output_dir.joinpath(f"backlink_car_{name}.tif"),
            )
        if walk:
            anisotropic_costdistance(
                src_friction=input_dir.joinpath("friction_walk.tif"),
                src_target=dest_raster,
                src_elevation=data.elevation,
                dst_cost=output_dir.joinpath(f"cost_walk_{name}.tif"),
                dst_nearest=output_dir.joinpath(f"nearest_walk_{name}.tif"),
                dst_backlink=output_dir.joinpath(f"backlink_walk_{name}.tif"),
            )

        for traveltimes in output_dir.glob("cost_*.tif"):
            seconds_to_minutes(traveltimes)


if __name__ == "__main__":
    cli()
