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

from datetime import datetime
import json
import os
from concurrent.futures import ThreadPoolExecutor
import shutil
import sys
from tempfile import TemporaryDirectory, gettempdir

import pytest
from appdirs import user_data_dir
import click
from loguru import logger
import rasterio
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely.geometry import shape

from geohealthaccess.cglc import CGLC, unique_tiles
from geohealthaccess.errors import MissingDataError
from geohealthaccess.geofabrik import Geofabrik
from geohealthaccess.gsw import GSW
from geohealthaccess.modeling import (
    anisotropic_costdistance,
    combine_speed,
    compute_friction,
    isotropic_costdistance,
    rasterize_destinations,
    speed_from_landcover,
    speed_from_roads,
    travel_obstacles,
)
from geohealthaccess.osm import thematic_extract, create_water_raster
from geohealthaccess.preprocessing import (
    compute_slope,
    concatenate_bands,
    create_grid,
    mask_raster,
    merge_tiles,
    reproject,
)
from geohealthaccess.srtm import SRTM
from geohealthaccess import storage
from geohealthaccess import qa
from geohealthaccess.utils import country_geometry, unzip
from geohealthaccess.worldpop import WorldPop


LOGFORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> <level>{level}</level> <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> {message}"

logger.remove()
logger.add(
    sys.stdout,
    format=LOGFORMAT,
    enqueue=True,
    backtrace=True,
    level="INFO",
)
logger.enable("")


@click.group()
def cli():
    """Map accessibility to health services."""
    pass


@cli.command()
def test():
    """Run test suite."""
    pytest.main(["tests"])


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
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def download(country, output_dir, earthdata_user, earthdata_pass, logs_dir, overwrite):
    """Download input datasets."""
    if not logs_dir:
        logs_dir = os.curdir
    else:
        os.makedirs(logs_dir, exist_ok=True)

    time = datetime.strftime(datetime.now(), "%Y-%m-%d_%H-%M-%S_%f")
    log_basename = f"geohealthaccess-download_{time}.log"
    log_file = os.path.join(logs_dir, log_basename)
    log_tmp = os.path.join(gettempdir(), log_basename)

    logger.add(
        log_tmp,
        format=LOGFORMAT,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
    )

    geom = country_geometry(country)

    # Set data directories automatically if they are not provided
    if not output_dir:
        output_dir = os.path.join(os.curdir, "data", "raw")
        logger.info(
            f"Output directory not provided. Using {os.path.abspath(output_dir)}."
        )

    # Create data directories
    worldpop_dir = os.path.join(output_dir, "worldpop")
    cglc_dir = os.path.join(output_dir, "cglc")
    osm_dir = os.path.join(output_dir, "osm")
    gsw_dir = os.path.join(output_dir, "gsw")
    srtm_dir = os.path.join(output_dir, "srtm")
    for data_dir in (worldpop_dir, cglc_dir, osm_dir, gsw_dir, srtm_dir):
        storage.mkdir(data_dir)

    # Population
    wp = WorldPop()
    wp.login()
    wp.download(country, worldpop_dir, overwrite=overwrite)
    wp.logout()

    # Land Cover
    cglc = CGLC()
    tiles = cglc.search(geom)
    for tile in tiles:
        cglc.download(tile, cglc_dir, overwrite=overwrite)

    # OpenStreetMap
    geofab = Geofabrik()
    region_id, _ = geofab.search(geom)
    geofab.download(region_id, osm_dir, overwrite=overwrite)

    # Global Surface WaterTrue
    gsw = GSW()
    tiles = gsw.search(geom)
    for tile in tiles:
        gsw.download(tile, "seasonality", gsw_dir, overwrite=overwrite)

    # Digital elevation model
    srtm = SRTM()
    srtm.authentify(earthdata_user, earthdata_pass)
    tiles = srtm.search(geom)
    with ThreadPoolExecutor(max_workers=5) as e:
        for i, tile in enumerate(tiles):
            e.submit(srtm.download, tile, srtm_dir, True, overwrite, i)

    # Write logs
    storage.cp(log_tmp, log_file)
    storage.rm(log_tmp)


@cli.command()
@click.option("--country", "-c", type=str, required=True, help="ISO A3 country code")
@click.option(
    "--crs",
    "-s",
    type=str,
    required=True,
    help="EPSG, PROJ or WKT CRS string",
)
@click.option(
    "--resolution", "-r", type=float, default=100, help="Pixel size in `crs` units"
)
@click.option("--input-dir", "-i", type=click.Path(), help="Input data directory")
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(),
    help="Output data directory",
)
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--quality-checks", is_flag=True, default=False, help="Enable quality checks"
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def preprocess(
    input_dir, output_dir, crs, resolution, country, logs_dir, quality_checks, overwrite
):
    """Preprocess and co-register input datasets."""
    if not logs_dir:
        logs_dir = os.curdir
    else:
        os.makedirs(logs_dir, exist_ok=True)

    time = datetime.strftime(datetime.now(), "%Y-%m-%d_%H-%M-%S_%f")
    log_basename = f"geohealthaccess-preprocessing_{time}.log"
    log_file = os.path.join(logs_dir, log_basename)
    log_tmp = os.path.join(gettempdir(), log_basename)

    logger.add(
        log_tmp,
        format=LOGFORMAT,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
    )

    # Set data directories if not provided and create them if necessary
    if not input_dir:
        input_dir = os.path.join(os.curdir, "data", "raw")
    if not output_dir:
        output_dir = os.path.join(os.curdir, "data", "input")
    for dir_ in (input_dir, output_dir):
        storage.mkdir(dir_)

    # Quality checks
    if quality_checks:
        logger.info("Checking input elevation data...")
        qa.srtm(os.path.join(input_dir, "srtm"))
        logger.info("Checking input land cover data...")
        qa.cglc(os.path.join(input_dir, "cglc"))
        logger.info("Checking input OpenStreetMap data...")
        qa.osm(os.path.join(input_dir, "osm"))
        logger.info("Checking input population data...")
        qa.worldpop(os.path.join(input_dir, "worldpop"))

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

    preprocess_land_cover(
        src_files=storage.glob(os.path.join(input_dir, "cglc", "*LC100*.zip")),
        dst_raster=os.path.join(output_dir, "land_cover.tif"),
        **args,
    )
    preprocess_elevation(
        src_files=storage.glob(os.path.join(input_dir, "srtm", "*SRTM*.hgt.zip")),
        dst_dir=output_dir,
        **args,
    )
    preprocess_osm(
        src_file=storage.glob(os.path.join(input_dir, "osm", "*.osm.pbf"))[0],
        dst_dir=output_dir,
        dst_crs=dst_crs,
        dst_shape=shape,
        dst_transform=transform,
        geom=geom,
        overwrite=overwrite,
    )
    preprocess_surface_water(
        src_files=storage.glob(os.path.join(input_dir, "gsw", "seasonality*.tif")),
        dst_raster=os.path.join(output_dir, "water.tif"),
        **args,
    )

    logger.info("Writing area of interest to disk.")
    with storage.open_(os.path.join(output_dir, "area_of_interest.geojson"), "w") as f:
        json.dump(geom.__geo_interface__, f)

    storage.cp(log_tmp, log_file)
    storage.rm(log_tmp)


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
    if storage.exists(dst_raster) and not overwrite:
        logger.info("Land cover data already preprocessed. Skipping.")
        return

    logger.info("Starting preprocessing of land cover data.")
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

    # some intermediary files must be stored in an user data directory
    # as the size will be too high when using a memory-based filesystem
    # for /tmp.
    tmp_data_dir = os.path.join(user_data_dir(appname="geohealthaccess"), "cglc")
    os.makedirs(tmp_data_dir, exist_ok=True)
    for src_file in src_files:
        dst_file = os.path.join(tmp_data_dir, os.path.basename(src_file))
        storage.cp(src_file, dst_file)
        unzip(dst_file, tmp_data_dir)

    reprojected_files = []
    tile_names = unique_tiles(tmp_data_dir)

    if not tile_names:
        raise MissingDataError("Land cover data not found.")

    for lc_class in LC_CLASSES:
        tiles = storage.glob(
            os.path.join(tmp_data_dir, f"*{lc_class}-coverfraction-layer*.tif")
        )
        if len(tiles) > 1:
            src_file = merge_tiles(
                tiles,
                os.path.join(tmp_data_dir, f"{lc_class}_mosaic.tif"),
                nodata=255,
            )
        else:
            src_file = tiles[0]
        reprojected_files.append(
            reproject(
                src_raster=src_file,
                dst_raster=os.path.join(tmp_data_dir, f"{lc_class}.tif"),
                dst_crs=dst_crs,
                dst_bounds=dst_bounds,
                dst_res=dst_res,
                src_nodata=255,
                dst_nodata=255,
                dst_dtype="Byte",
                resampling_method="cubic",
                overwrite=True,
            )
        )

    if len(reprojected_files) > 1:
        raster = concatenate_bands(
            src_files=reprojected_files,
            dst_file=os.path.join(tmp_data_dir, os.path.basename(dst_raster)),
            band_descriptions=LC_CLASSES,
        )
    else:
        raster = reprojected_files[0]

    if geom:
        mask_raster(raster, geom)

    storage.cp(raster, dst_raster)
    shutil.rmtree(tmp_data_dir)


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
    logger.info("Starting preprocessing of OSM data.")

    # Source files are copied into a temporary directory where processed data
    # is also going to be stored.
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        tmp_src_file = os.path.join(tmp_dir, os.path.basename(src_file))
        storage.cp(src_file, tmp_src_file)

        # Extract roads, health facilities, water objects and ferries
        # from the main OSM data file.
        for theme in ("roads", "health", "water", "ferry"):
            dst_file = os.path.join(dst_dir, f"{theme}.gpkg")
            tmp_dst_file = os.path.join(tmp_dir, os.path.basename(dst_file))

            # Skip processing if destination file already exists
            if storage.exists(dst_file) and not overwrite:
                logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
                continue

            # Extract objects and copy output file into destination directory
            try:
                thematic_extract(tmp_src_file, theme, tmp_dst_file)
                storage.cp(tmp_dst_file, dst_file)
            except MissingDataError:
                logger.warning(
                    f"Skipping extraction of `{theme}` objects due to missing data."
                )

        # Create water raster from OSM data
        # Get data from destination directory if not present anymore
        # in the temporary directory.
        water_gpkg = os.path.join(tmp_dir, "water.gpkg")
        if not os.path.isfile(water_gpkg):
            storage.cp(os.path.join(dst_dir, "water.gpkg"), water_gpkg)
        tmp_water_raster = os.path.join(tmp_dir, "water_osm.tif")
        create_water_raster(
            os.path.join(tmp_dir, "water.gpkg"),
            tmp_water_raster,
            dst_crs,
            dst_shape,
            dst_transform,
            include_streams=False,
            geom=geom,
            overwrite=overwrite,
        )
        if geom:
            mask_raster(tmp_water_raster, geom)

        # Copy temporary file to destination directory
        storage.cp(tmp_water_raster, os.path.join(dst_dir, "water_osm.tif"))


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
    # Skip processing if surface_water.tif already exists
    if storage.exists(dst_raster) and not overwrite:
        logger.info(f"{os.path.basename(dst_raster)} already exists. Skipping.")
        return

    # Copy GSW tiles into a temporary directory before processing
    logger.info("Starting preprocessing of surface water data.")
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        tmp_src_files = []
        for src_file in src_files:
            tmp_src_file = os.path.join(tmp_dir, os.path.basename(src_file))
            storage.cp(src_file, os.path.join(tmp_dir, os.path.basename(src_file)))
            tmp_src_files.append(tmp_src_file)

        # Merge tiles if necessary
        if len(tmp_src_files) > 1:
            mosaic = merge_tiles(
                tmp_src_files, os.path.join(tmp_dir, "mosaic.tif"), nodata=255
            )

        else:
            mosaic = tmp_src_files[0]

        tmp_dst_file = os.path.join(
            tmp_dir, os.path.basename(dst_raster).replace(".tif", "_reprojected.tif")
        )
        tmp_dst_file = reproject(
            src_raster=mosaic,
            dst_raster=tmp_dst_file,
            dst_crs=dst_crs,
            dst_bounds=dst_bounds,
            dst_res=dst_res,
            src_nodata=255,
            dst_nodata=255,
            dst_dtype="Byte",
            resampling_method="max",
            overwrite=True,
        )
        if geom:
            mask_raster(tmp_dst_file, geom)

        # Copy output raster to destination directory
        storage.cp(tmp_dst_file, dst_raster)


def preprocess_elevation(
    src_files, dst_dir, dst_crs, dst_bounds, dst_res, geom=None, overwrite=False
):
    """Preprocess input elevation data.

    Creates elevation and slope rasters from SRTM tiles.

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
    logger.info("Starting preprocessing of elevation data.")
    dst_dem = os.path.join(dst_dir, "elevation.tif")
    dst_slope = os.path.join(dst_dir, "slope.tif")
    all_exists = all([storage.exists(f) for f in (dst_dem, dst_slope)])
    if all_exists and not overwrite:
        logger.info("All topograpy rasters already exists. Skipping processing.")
        return

    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        # unzip all tiles in a temporary directory
        for tile in src_files:
            storage.unzip(tile, tmpdir)

        # merge tiles into a single mosaic if necessary
        tiles = storage.glob(os.path.join(tmpdir, "*.hgt"))
        if len(tiles) > 1:
            dem = merge_tiles(tiles, os.path.join(tmpdir, "mosaic.tif"), nodata=-32768)
        else:
            dem = tiles[0]

        # compute slope before reprojection
        if not storage.exists(dst_slope) or overwrite:
            slope = compute_slope(
                dem, os.path.join(tmpdir, "slope.tif"), percent=False, scale=111120
            )
        else:
            logger.info("Slope raster already exists. Skipping processing.")
            slope = dst_slope

        for src, dst in zip((dem, slope), (dst_dem, dst_slope)):

            if storage.exists(dst) and not overwrite:
                logger.info(
                    f"{os.path.basename(dst)} already exists. Skipping processing."
                )
                continue

            # dtype is Int16 for elevation, and Float32 for slope & aspect
            nodata = -9999
            dtype = "Float32"
            if "elevation" in dst:
                nodata = -32768
                dtype = "Int16"

            dst_tmp = os.path.join(
                tmpdir, os.path.basename(dst).replace(".tif", "_reprojected.tif")
            )

            dst_tmp = reproject(
                src_raster=src,
                dst_raster=dst_tmp,
                dst_crs=dst_crs,
                dst_bounds=dst_bounds,
                dst_res=dst_res,
                src_nodata=nodata,
                dst_nodata=nodata,
                dst_dtype=dtype,
                resampling_method="cubic",
                overwrite=True,
            )
            if geom:
                mask_raster(dst_tmp, geom)

            storage.cp(dst_tmp, dst)


@cli.command()
@click.option("--input-dir", "-i", type=click.Path(), help="Input data directory")
@click.option("--interm-dir", type=click.Path(), help="Intermediary data directory")
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
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--quality-checks", is_flag=True, default=False, help="Enable quality checks"
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def access(
    input_dir,
    interm_dir,
    output_dir,
    car,
    walk,
    bike,
    travel_speeds,
    destinations,
    logs_dir,
    quality_checks,
    overwrite,
):
    """Map travel times to the provided health facilities."""
    if not logs_dir:
        logs_dir = os.curdir
    else:
        os.makedirs(logs_dir, exist_ok=True)

    time = datetime.strftime(datetime.now(), "%Y-%m-%d_%H-%M-%S_%f")
    log_basename = f"geohealthaccess-access_{time}.log"
    log_file = os.path.join(logs_dir, log_basename)
    log_tmp = os.path.join(gettempdir(), log_basename)

    logger.add(
        log_tmp,
        format=LOGFORMAT,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
    )

    # Set data directories if not provided and create them if necessary
    if not input_dir:
        input_dir = os.path.join(os.curdir, "data", "input")
    if not interm_dir:
        interm_dir = os.path.join(os.curdir, "data", "intermediary")
    if not output_dir:
        output_dir = os.path.join(os.curdir, "data", "output")
    for dir_ in (input_dir, interm_dir, output_dir):
        storage.mkdir(dir_)

    aoi_path = os.path.join(input_dir, "area_of_interest.geojson")
    with storage.open_(aoi_path) as f:
        aoi = shape(json.load(f))

    # Quality checks
    if quality_checks:
        logger.info("Validating raster grid...")
        qa.grid(input_dir)
        logger.info("Checking elevation raster...")
        qa.elevation(input_dir, aoi)
        logger.info("Checking land cover raster...")
        qa.land_cover(input_dir, aoi)
        logger.info("Checking roads geopackage...")
        qa.roads(input_dir, aoi)
        logger.info("Checking water raster...")
        qa.water(input_dir, aoi)

    # Use default travel speeds if JSON file is not provided
    if not travel_speeds:
        travel_speeds = resource_filename(__name__, "resources/travel-speeds.json")
    with storage.open_(travel_speeds) as f:
        travel_speeds = json.load(f)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        # Get raster grid from input land cover raster
        land_cover = os.path.join(tmp_dir, "land_cover.tif")
        storage.cp(os.path.join(input_dir, "land_cover.tif"), land_cover)
        with rasterio.open(land_cover) as src:
            dst_transform = src.transform
            dst_crs = src.crs
            dst_width = src.width
            dst_height = src.height

        # Compute a raster with all non-passable pixels based on water and slope
        water_gsw = os.path.join(tmp_dir, "water_gsw.tif")
        water_osm = os.path.join(tmp_dir, "water_osm.tif")
        elevation = os.path.join(tmp_dir, "elevation.tif")
        slope = os.path.join(tmp_dir, "slope.tif")
        storage.cp(os.path.join(input_dir, "water.tif"), water_gsw)
        storage.cp(os.path.join(input_dir, "water_osm.tif"), water_osm)
        storage.cp(os.path.join(input_dir, "elevation.tif"), elevation)
        storage.cp(os.path.join(input_dir, "slope.tif"), slope)
        obstacles = travel_obstacles(
            src_water=(water_gsw, water_osm),
            src_slope=slope,
            dst_file=os.path.join(tmp_dir, "obstacle.tif"),
            max_slope=35,
            overwrite=overwrite,
        )

        # Create speed rasters from land cover and road network
        landcover_speed = speed_from_landcover(
            land_cover,
            dst_file=os.path.join(tmp_dir, "speed_landcover.tif"),
            speeds=travel_speeds["land-cover"],
            overwrite=overwrite,
        )
        roads = os.path.join(tmp_dir, "roads.gpkg")
        ferry = os.path.join(tmp_dir, "ferry.gpkg")
        storage.cp(os.path.join(input_dir, "roads.gpkg"), roads)
        if storage.exists(os.path.join(input_dir, "ferry.gpkg")):
            storage.cp(os.path.join(input_dir, "ferry.gpkg"), ferry)
        else:
            ferry = None
        transport_speed = speed_from_roads(
            roads,
            dst_file=os.path.join(tmp_dir, "speed_transport.tif"),
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_width=dst_width,
            dst_height=dst_height,
            src_ferry=ferry,
            speeds=travel_speeds["transport"],
            overwrite=overwrite,
        )

        # Clean temporary directory
        for f in (land_cover, water_gsw, water_osm, slope, roads):
            os.remove(f)

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
                dst_file=os.path.join(tmp_dir, f"speed_{mode}.tif"),
                mode=mode,
            )

            friction = compute_friction(
                speed,
                dst_file=os.path.join(tmp_dir, f"friction_{mode}.tif"),
                max_time=3600,
                one_meter=mode == "walk",
            )

            mask_raster(friction, aoi)

            storage.cp(landcover_speed, os.path.join(interm_dir, "landcover_speed.tif"))
            storage.cp(transport_speed, os.path.join(interm_dir, "transport_speed.tif"))
            storage.cp(obstacles, os.path.join(interm_dir, "obstacle.tif"))
            storage.cp(friction, os.path.join(interm_dir, f"friction_{mode}.tif"))

            # Clean temporary directory
            for f in (landcover_speed, transport_speed, obstacles):
                os.remove(f)

        if not destinations:
            osm_health = os.path.join(tmp_dir, "health.gpkg")
            storage.cp(os.path.join(input_dir, "health.gpkg"), osm_health)
            destinations = [osm_health]

        for features in destinations:

            basename = os.path.basename(features)
            name, ext = os.path.splitext(basename)
            features_tmp = os.path.join(tmp_dir, basename)
            if not os.path.isfile(features_tmp):
                storage.cp(features, features_tmp)
            dst_file_tmp = os.path.join(tmp_dir, f"{name}.tif")
            dest_raster = rasterize_destinations(
                features_tmp,
                dst_file_tmp,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_height=dst_height,
                dst_width=dst_width,
                overwrite=overwrite,
            )
            mask_raster(dest_raster, aoi)

            if car:
                isotropic_costdistance(
                    src_friction=os.path.join(tmp_dir, "friction_car.tif"),
                    src_target=dest_raster,
                    dst_cost=os.path.join(tmp_dir, f"cost_car_{name}.tif"),
                    dst_nearest=os.path.join(tmp_dir, f"nearest_car_{name}.tif"),
                    dst_backlink=os.path.join(tmp_dir, f"backlink_car_{name}.tif"),
                )
            if walk:
                elevation = os.path.join(tmp_dir, "elevation.tif")
                storage.cp(os.path.join(input_dir, "elevation.tif"), elevation)
                anisotropic_costdistance(
                    src_friction=os.path.join(tmp_dir, "friction_walk.tif"),
                    src_target=dest_raster,
                    src_elevation=elevation,
                    dst_cost=os.path.join(tmp_dir, f"cost_walk_{name}.tif"),
                    dst_nearest=os.path.join(tmp_dir, f"nearest_walk_{name}.tif"),
                    dst_backlink=os.path.join(tmp_dir, f"backlink_walk_{name}.tif"),
                )

        for output in ("cost", "nearest", "backlink"):
            rasters = storage.glob(os.path.join(tmp_dir, f"{output}*.tif"))
            for raster in rasters:
                src = os.path.join(tmp_dir, os.path.basename(raster))
                dst = os.path.join(output_dir, os.path.basename(raster))
                storage.cp(src, dst)

    # Write logs
    storage.cp(log_tmp, log_file)
    storage.rm(log_tmp)

    # quality check
    if quality_checks:
        qa.cost(output_dir, aoi)


if __name__ == "__main__":
    cli()
