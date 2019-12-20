"""Automatically download input data for a given country."""

import argparse
import os

from geohealthaccess import utils, srtm, cglc, gsw, worldpop, geofabrik
from geohealthaccess.config import load_config


def _empty(directory):
    """Check if a directory is empty."""
    return len(os.listdir(directory)) == 0


def download(country, dst_dir, earthdata_username,
             earthdata_password, overwrite=False):
    """Download input data for a given country.

    Parameters
    ----------
    country : str
        Three-letters country code.
    dst_dir : str
        Output directory.
    earthdata_username : str
        NASA Earthdata username.
    earthdata_password : str
        NASA Earthdata password.
    overwrite : bool, optional
        Overwrite existing data.
    """
    # Get country geometry
    geom = utils.country_geometry(country.lower())

    # Elevation
    output_dir = os.path.join(dst_dir, 'elevation')
    os.makedirs(output_dir, exist_ok=True)
    if _empty(output_dir) or overwrite:
        print('Downloading elevation data...')
        srtm.download(geom, output_dir, earthdata_username, earthdata_password)
        utils.unzip_all(output_dir, remove_archives=True)
    else:
        print('Elevation data already downloaded. Skipping...')


    # Land cover
    output_dir = os.path.join(dst_dir, 'land_cover')
    os.makedirs(output_dir, exist_ok=True)
    if _empty(output_dir) or overwrite:
        print('Downloading land cover data...')
        cglc.download(geom, output_dir)
        utils.unzip_all(output_dir, remove_archives=True)
    else:
        print('Land cover data already downloaded. Skipping...')

    # Water
    output_dir = os.path.join(dst_dir, 'water')
    os.makedirs(output_dir, exist_ok=True)
    if _empty(output_dir) or overwrite:
        print('Downloading surface water data...')
        gsw.download(geom, 'seasonality', output_dir)
    else:
        print('Surface water data already downloaded. Skipping...')

    # Population
    output_dir = os.path.join(dst_dir, 'population')
    os.makedirs(output_dir, exist_ok=True)
    if _empty(output_dir) or overwrite:
        worldpop.download(country, 2018, output_dir)
    else:
        print('Population data already downloaded. Skipping...')

    # OpenStreetMap road network
    output_dir = os.path.join(dst_dir, 'openstreetmap')
    os.makedirs(output_dir, exist_ok=True)
    if _empty(output_dir) or overwrite:
        print('Downloading OpenStreetMap data...')
        spatial_index = geofabrik.get_spatial_index()
        region_id, _ = geofabrik.find_best_region(spatial_index, geom)
        geofabrik.download_latest_highways(region_id, output_dir, overwrite=True)
    else:
        print('OpenStreetMap data already downloaded. Skipping...')

    print('Done!')
    return


def main():
    # Parse command-line argument & load configuration
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'config_file',
        type=str,
        help='.ini configuration file')
    args = parser.parse_args()
    conf = load_config(args.config_file)
    # Run script
    download(
        country=conf['AREA']['CountryCode'],
        dst_dir=conf['DIRECTORIES']['InputDir'],
        earthdata_username=conf['EARTHDATA']['EarthdataUsername'],
        earthdata_password=conf['EARTHDATA']['EarthdataPassword']
    )


if __name__ == '__main__':
    main()