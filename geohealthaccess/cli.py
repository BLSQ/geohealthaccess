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

import click

from geohealthaccess.cglc import CGLC
from geohealthaccess.geofabrik import SpatialIndex
from geohealthaccess.gsw import GSW
from geohealthaccess.srtm import SRTM
from geohealthaccess.utils import country_geometry
from geohealthaccess.worldpop import WorldPop


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

    # Global Surface Water
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
    for tile in tiles:
        srtm.download(tile, os.path.join(output_dir, NAMES[4]), overwrite=overwrite)


if __name__ == "__main__":
    cli()
