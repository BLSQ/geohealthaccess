"""Automatically download input data for a given country."""

import argparse
import os

from geohealthaccess import utils, srtm, cglc, gsw, worldpop, geofabrik
from geohealthaccess.config import load_config


def download(country, dst_dir, earthdata_username, earthdata_password):
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
    """
    # Get country geometry
    geom = utils.country_geometry(country.lower())

    # Elevation
    print('Downloading elevation data...')
    output_dir = os.path.join(dst_dir, 'elevation')
    os.makedirs(output_dir, exist_ok=True)
    srtm.download(geom, output_dir, earthdata_username, earthdata_password)
    utils.unzip_all(output_dir, remove_archives=True)

    # Land cover
    print('Downloading land cover data...')
    output_dir = os.path.join(dst_dir, 'land_cover')
    os.makedirs(output_dir, exist_ok=True)
    cglc.download(geom, output_dir)
    utils.unzip_all(output_dir, remove_archives=True)

    # Water
    print('Downloading surface water data...')
    output_dir = os.path.join(dst_dir, 'water')
    os.makedirs(output_dir, exist_ok=True)
    gsw.download(geom, 'seasonality', output_dir)

    # Population
    print('Downloading population data...')
    output_dir = os.path.join(dst_dir, 'population')
    os.makedirs(output_dir, exist_ok=True)
    worldpop.download(country, 2018, output_dir)

    # OpenStreetMap road network
    print('Downloading OpenStreetMap data...')
    output_dir = os.path.join(dst_dir, 'openstreetmap')
    os.makedirs(output_dir, exist_ok=True)
    spatial_index = geofabrik.build_spatial_index()
    region_id, _ = geofabrik.find_best_region(spatial_index, geom)
    geofabrik.download_latest_highways(region_id, output_dir, overwrite=True)

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