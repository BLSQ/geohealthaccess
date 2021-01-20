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
from pathlib import Path
import sys
from tempfile import TemporaryDirectory, tempdir

import click
from loguru import logger
import rasterio
from pkg_resources import resource_filename
from rasterio.crs import CRS
from shapely.geometry import shape

from geohealthaccess.cglc import CGLC, unique_tiles
from geohealthaccess.data import Intermediary, Raw
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
    compute_aspect,
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
    sys.stdout, format=LOGFORMAT, enqueue=True, backtrace=True, level="INFO",
)
logger.enable("")


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
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def download(country, output_dir, earthdata_user, earthdata_pass, logs_dir, overwrite):
    """Download input datasets."""
    if not logs_dir:
        logs_dir = os.curdir

    time = datetime.strftime(datetime.now(), "%Y-%m-%d_%H-%M-%S_%f")
    log_basename = f"geohealthaccess-download_{time}.log"
    log_file = os.path.join(logs_dir, log_basename)
    log_tmp = os.path.join(tempdir, log_basename)

    logger.add(
        log_tmp, format=LOGFORMAT, enqueue=True, backtrace=True, level="DEBUG",
    )

    geom = country_geometry(country)

    # Set data directories automatically if they are not provided
    if not output_dir:
        output_dir = os.path.join(os.curdir, "Data", "Input")
        logger.info(
            f"Output directory not provided. Using {os.path.abspath(output_dir)}."
        )

    # Create data directories
    NAMES = ("Population", "Land_Cover", "OpenStreetMap", "Surface_Water", "Elevation")
    datadirs = [os.path.join(output_dir, name) for name in NAMES]
    for datadir in datadirs:
        storage.mkdir(datadir)

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
    geofab = Geofabrik()
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
    with ThreadPoolExecutor(max_workers=5) as e:
        for i, tile in enumerate(tiles):
            e.submit(
                srtm.download, tile, dst_dir, True, overwrite, i,
            )

    # Write logs
    storage.cp(log_tmp, log_file)
    storage.rm(log_tmp)


@cli.command()
@click.option("--country", "-c", type=str, required=True, help="ISO A3 country code")
@click.option(
    "--crs", "-s", type=str, required=True, help="EPSG, PROJ or WKT CRS string",
)
@click.option(
    "--resolution", "-r", type=float, default=100, help="Pixel size in `crs` units"
)
@click.option("--input-dir", "-i", type=click.Path(), help="Input data directory")
@click.option(
    "--output-dir", "-o", type=click.Path(), help="Output data directory",
)
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--skip-qa", "-q", is_flag=True, default=False, help="Skip input data checks"
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def preprocess(
    input_dir, output_dir, crs, resolution, country, logs_dir, skip_qa, overwrite
):
    """Preprocess and co-register input datasets."""
    if not logs_dir:
        logs_dir = os.curdir

    logger.add(
        os.path.join(logs_dir, "geohealthaccess-preprocessing_{time}.log"),
        format=LOGFORMAT,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
    )

    # Set data directories if not provided and create them if necessary
    if not input_dir:
        input_dir = os.path.join(os.curdir, "Data", "Input")
    if not output_dir:
        output_dir = os.path.join(os.curdir, "Data", "Intermediary")
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    for p in (input_dir, output_dir):
        p.mkdir(parents=True, exist_ok=True)

    # Quality checks
    if not skip_qa:
        logger.info("Checking input elevation data...")
        qa.srtm(os.path.join(input_dir, "Elevation"))
        logger.info("Checking input land cover data...")
        qa.cglc(os.path.join(input_dir, "Land_Cover"))
        logger.info("Checking input OpenStreetMap data...")
        qa.osm(os.path.join(input_dir, "OpenStreetMap"))
        logger.info("Checking input population data...")
        qa.worldpop(os.path.join(input_dir, "Population"))

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
        dst_raster=output_dir.joinpath("land_cover.tif").as_posix(),
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
        dst_raster=output_dir.joinpath("surface_water.tif").as_posix(),
        **args,
    )

    logger.info("Writing area of interest to disk.")
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
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        tmpdir = Path(tmpdir)
        for tile in src_files:
            unzip(tile, tmpdir)

        reprojected_files = []
        tile_names = unique_tiles(tmpdir)

        if not tile_names:
            raise MissingDataError("Land cover data not found.")

        for lc_class in LC_CLASSES:
            tiles = [
                p.as_posix()
                for p in tmpdir.glob(f"*{lc_class}-coverfraction-layer*.tif")
            ]
            if len(tiles) > 1:
                src_file = merge_tiles(
                    tiles, os.path.join(tmpdir, f"{lc_class}_mosaic.tif"), nodata=255,
                )
            else:
                src_file = tiles[0]
            reprojected_files.append(
                reproject(
                    src_raster=src_file,
                    dst_raster=os.path.join(tmpdir, f"{lc_class}.tif"),
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
            raster = concatenate_bands(
                src_files=reprojected_files,
                dst_file=dst_raster,
                band_descriptions=LC_CLASSES,
            )
        else:
            raster = reprojected_files[0]

        if geom:
            mask_raster(raster, geom)


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
    for theme in ("roads", "health", "water", "ferry"):
        dst_file = os.path.join(dst_dir, f"{theme}.gpkg")
        if os.path.isfile(dst_file) and not overwrite:
            logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
            continue
        try:
            thematic_extract(src_file, theme, dst_file)
        except MissingDataError:
            logger.warning(
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
        logger.info(f"{os.path.basename(dst_raster)} already exists. Skipping.")
        return
    logger.info("Starting preprocessing of surface water data.")
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
    logger.info("Starting preprocessing of elevation data.")
    dst_dem = os.path.join(dst_dir, "elevation.tif")
    dst_slope = os.path.join(dst_dir, "slope.tif")
    dst_aspect = os.path.join(dst_dir, "aspect.tif")
    all_exists = all([os.path.isfile(f) for f in (dst_dem, dst_slope, dst_aspect)])
    if all_exists and not overwrite:
        logger.info("All topograpy rasters already exists. Skipping processing.")
        return

    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        # unzip all tiles in a temporary directory
        tmpdir = Path(tmpdir)
        for tile in src_files:
            unzip(tile, tmpdir)

        # merge tiles into a single mosaic if necessary
        tiles = [f.as_posix() for f in tmpdir.glob("*.hgt")]
        if len(tiles) > 1:
            dem = merge_tiles(tiles, os.path.join(tmpdir, "mosaic.tif"), nodata=-32768)
        else:
            dem = tiles[0]

        # compute slope and aspect before reprojection
        if not os.path.isfile(dst_slope) or overwrite:
            slope = compute_slope(
                dem, os.path.join(tmpdir, "slope.tif"), percent=False, scale=111120
            )
        else:
            logger.info("Slope raster already exists. Skipping processing.")
            slope = dst_slope
        if not os.path.isfile(dst_aspect) or overwrite:
            aspect = compute_aspect(
                dem, os.path.join(tmpdir, "aspect.tif"), trigonometric=True
            )
        else:
            logger.info("Aspect raster already exists. Skipping processing.")
            aspect = dst_aspect

        for src, dst in zip((dem, slope, aspect), (dst_dem, dst_slope, dst_aspect)):

            if os.path.isfile(dst) and not overwrite:
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
@click.option("--logs-dir", "-l", type=click.Path(), help="Logs output directory")
@click.option(
    "--skip-qa", "-q", is_flag=True, default=False, help="Skip quality checks"
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="Overwrite existing files"
)
def access(
    input_dir,
    output_dir,
    car,
    walk,
    bike,
    travel_speeds,
    destinations,
    logs_dir,
    skip_qa,
    overwrite,
):
    """Map travel times to the provided health facilities."""
    if not logs_dir:
        logs_dir = os.curdir

    logger.add(
        os.path.join(logs_dir, "geohealthaccess-access_{time}.log"),
        format=LOGFORMAT,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
    )

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

    # Quality checks
    if not skip_qa:
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
        dst_file=input_dir.joinpath("obstacle.tif").as_posix(),
        max_slope=35,
        overwrite=overwrite,
    )
    landcover_speed = speed_from_landcover(
        data.land_cover,
        dst_file=input_dir.joinpath("landcover_speed.tif").as_posix(),
        speeds=travel_speeds["land-cover"],
        overwrite=overwrite,
    )
    transport_speed = speed_from_roads(
        data.roads,
        dst_file=input_dir.joinpath("transport_speed.tif").as_posix(),
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
            dst_file=input_dir.joinpath(f"speed_{mode}.tif").as_posix(),
            mode=mode,
        )

        friction = compute_friction(
            speed,
            dst_file=input_dir.joinpath(f"friction_{mode}.tif").as_posix(),
            max_time=3600,
            one_meter=mode == "walk",
        )
        mask_raster(friction, aoi)

    if not destinations:
        destinations = [data.health]

    for features in destinations:

        basename = os.path.basename(features)
        name, ext = os.path.splitext(basename)
        dst_file = input_dir.joinpath(f"{name}.tif").as_posix()
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
                src_friction=input_dir.joinpath("friction_car.tif").as_posix(),
                src_target=dest_raster,
                dst_cost=output_dir.joinpath(f"cost_car_{name}.tif").as_posix(),
                dst_nearest=output_dir.joinpath(f"nearest_car_{name}.tif").as_posix(),
                dst_backlink=output_dir.joinpath(f"backlink_car_{name}.tif").as_posix(),
            )
        if walk:
            anisotropic_costdistance(
                src_friction=input_dir.joinpath("friction_walk.tif").as_posix(),
                src_target=dest_raster,
                src_elevation=data.elevation,
                dst_cost=output_dir.joinpath(f"cost_walk_{name}.tif").as_posix(),
                dst_nearest=output_dir.joinpath(f"nearest_walk_{name}.tif").as_posix(),
                dst_backlink=output_dir.joinpath(
                    f"backlink_walk_{name}.tif"
                ).as_posix(),
            )

        # for traveltimes in output_dir.glob("cost_*.tif"):
        #    seconds_to_minutes(traveltimes)

    # quality check
    if not skip_qa:
        qa.cost(output_dir, aoi)


if __name__ == "__main__":
    cli()
