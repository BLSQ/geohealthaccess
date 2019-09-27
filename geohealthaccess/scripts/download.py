"""Download input data."""

import os

import click
from geohealthaccess import utils, srtm, cglc, gsw, worldpop


@click.command()
@click.option(
    '--country', '-c', type=str, help='Country code.')
@click.option(
    '--directory', '-d', type=click.Path(), help='Output directory.')
@click.option(
    '--earthdata-user', '-u', type=str, help='NASA EarthData username.',
    default=lambda: os.environ.get('EARTHDATA_USERNAME', ''))
@click.option(
    '--earthdata-pass', '-p', type=str, help='NASA EarthData password.',
    default=lambda: os.environ.get('EARTHDATA_PASSWORD', ''))
def download(country, directory, earthdata_user, earthdata_pass):
    """Download all input data."""
    country = country.lower()
    geom = utils.country_geometry(country)

    # Topography
    click.echo('Downloading topographic data...')
    output_dir = os.path.join(directory, country, 'input', 'topography')
    os.makedirs(output_dir, exist_ok=True)
    srtm.download(geom, output_dir, earthdata_user, earthdata_pass)
    click.echo('Unzipping...')
    utils.unzip_all(output_dir)

    # Land cover
    click.echo('Downloading land cover data...')
    output_dir = os.path.join(directory, country, 'input', 'land_cover')
    os.makedirs(output_dir, exist_ok=True)
    cglc.download(geom, output_dir)
    click.echo('Unzipping...')
    utils.unzip_all(output_dir)

    # Water
    click.echo('Downloading surface water data...')
    output_dir = os.path.join(directory, country, 'input', 'water')
    os.makedirs(output_dir, exist_ok=True)
    gsw.download(geom, 'seasonality', output_dir)

    # Population
    click.echo('Downloading population data...')
    output_dir = os.path.join(directory, country, 'input', 'population')
    os.makedirs(output_dir, exist_ok=True)
    worldpop.download(country, 2018, output_dir)

    click.echo('Input data downloaded.')

    return directory