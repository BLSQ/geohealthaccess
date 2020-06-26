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

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import logging
from itertools import product
from tempfile import TemporaryDirectory

import click
from rasterio.crs import CRS

from geohealthaccess.cglc import CGLC, unique_tiles
from geohealthaccess.geofabrik import SpatialIndex
from geohealthaccess.gsw import GSW
from geohealthaccess.srtm import SRTM
from geohealthaccess.utils import country_geometry, unzip
from geohealthaccess.worldpop import WorldPop
from geohealthaccess.osm import thematic_extract
from geohealthaccess.errors import MissingDataError
from geohealthaccess.preprocessing import (
    create_grid,
    reproject,
    merge_tiles,
    concatenate_bands,
    compute_slope,
    compute_aspect,
)
from geohealthaccess.data import Raw


log = logging.getLogger(__name__)


@click.group()
def cli():
    """Map accessibility to health services."""
    pass


@cli.command()
@click.option("--country", "-c", required=True, type=str, help="ISO A3 country code")
@click.option(
    "--output-dir", "-o", required=True, type=click.Path(), help="Output directory"
)
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
        input_dir = os.path.join(os.curdir, "Input")
    if not output_dir:
        output_dir = os.path.join(os.curdir, "Intermediary")
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
    }

    raw = Raw(input_dir)
    dst_landcover = output_dir.joinpath("land_cover.tif")
    preprocess_land_cover(raw.land_cover, dst_landcover, **args)
    preprocess_elevation(raw.elevation, output_dir, **args)
    preprocess_osm(raw.openstreetmap[0], output_dir)
    dst_surfacewater = output_dir.joinpath("surface_water.tif")
    preprocess_surface_water(raw.surface_water, dst_surfacewater, **args)


def preprocess_land_cover(
    src_files, dst_raster, dst_crs, dst_bounds, dst_res, overwrite=False
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
    overwrite : bool, optional
        Overwrite existing files.
    """
    if os.path.isfile(dst_raster) and not overwrite:
        log.info("Land cover data already preprocessed. Skipping.")
        return
    log.info("Starting preprocessing of land cover data.")
    LC_CLASSES = ["bare", "crops", "grass", "moss", "shrub", "tree", "urban"]
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        tmpdir = Path(tmpdir)
        for tile in src_files:
            unzip(tile, tmpdir)

        reprojected_files = []
        tile_names = unique_tiles(tmpdir)
        log.info(f"Found {len(tile_names)} unique CGLC tiles to process.")
        for tile_name, lc_class in product(tile_names, LC_CLASSES):
            tiles = list(tmpdir.glob(f"{tile_name}*{lc_class}-coverfraction*.tif"))
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
            concatenate_bands(
                src_files=reprojected_files,
                dst_file=dst_raster,
                band_descriptions=LC_CLASSES,
            )


def preprocess_osm(src_file, dst_dir, overwrite=False):
    """Preprocess input OSM data.

    Parameters
    ----------
    src_file : str
        Path to source .osm.pbf file.
    dst_dir : str
        Path to output directory.
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


def preprocess_surface_water(
    src_files, dst_raster, dst_crs, dst_bounds, dst_res, overwrite=False
):
    """Preprocess input surface water data.

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
        reproject(
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


def preprocess_elevation(
    src_files, dst_dir, dst_crs, dst_bounds, dst_res, overwrite=False
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
            slope = compute_slope(dem, tmpdir.joinpath("slope.tif"), percent=False)
        else:
            log.info("Slope raster already exists. Skipping processing.")
        if not os.path.isfile(dst_aspect) or overwrite:
            aspect = compute_aspect(
                dem, tmpdir.joinpath("aspect.tif"), trigonometric=True
            )
        else:
            log.info("Aspect raster already exists. Skipping processing.")

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

            reproject(
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


if __name__ == "__main__":
    cli()
