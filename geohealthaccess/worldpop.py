"""Acquisition and preprocessing of WorldPop population data."""

import os
import logging

from geohealthaccess.utils import download_from_ftp


log = logging.getLogger(__name__)

FTP_HOST = "ftp.worldpop.org.uk"
BASE_DIR = "GIS/Population/Global_2000_2020"


def build_url(country, year):
    """Build download path for WorldPop 100m population data.

    Parameters
    ----------
    country : str
        Country ISO A3 code (example: 'COD').
    year : int
        Year of interest (between 2000 and 2020).
    
    Returns
    -------
    remote_path : tuple of str
        Path to remote file: (directory, filename).
    """
    directory = f"{BASE_DIR}/{year}/{country.upper()}"
    filename = f"{country.lower()}_ppp_{year}.tif"
    return f"ftp://{FTP_HOST}/{directory}/{filename}"


def download(country, year, output_dir, overwrite=False):
    """Download WorldPop 100m population data for a given
    year and country.

    Parameters
    ----------
    country : str
        Country ISO A3 code (example: 'COD').
    year : int
        Year of interest (between 2000 and 2020).
    
    Returns
    -------
    local_path : str
        Path to downloaded file.
    """
    url = build_url(country, year)
    log.info(f"Downloading worldpop data from URL {url}.")
    local_path = download_from_ftp(url, output_dir)
    log.info(f"Downloaded worldpop data to {os.path.abspath(local_path)}.")
    return local_path
