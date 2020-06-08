"""Acquisition and preprocessing of WorldPop population data."""

import logging
import os
from collections import namedtuple
from ftplib import FTP

from geohealthaccess.utils import download_from_ftp

log = logging.getLogger(__name__)

FTP_HOST = "ftp.worldpop.org.uk"
BASE_DIR = "GIS/Population/Global_2000_2020"


def list_available_years(country):
    """List available years for Worldpop population data for a given
    country identified by its 3-letter country code.
    """
    years = []
    ftp = FTP(FTP_HOST)
    ftp.login()
    listdir = ftp.nlst("GIS/Population/Global_2000_2020/")
    for path in listdir:
        fname = path.split("/")[-1]
        if fname.isnumeric() and len(fname) == 4:
            years.append(int(fname))
    return years
    ftp.close()


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


def download(country, output_dir, year=None, overwrite=False):
    """Download WorldPop 100m population data for a given country.
    Automatically get latest data if year is not specified.

    Parameters
    ----------
    country : str
        Country ISO A3 code (example: 'COD').
    output_dir : str
        Path to output directory.
    year : int, optional
        Year of interest (between 2000 and 2020). If not specified,
        latest year available is used.
    overwrite : bool, optional
        Force overwrite of existing data.
    
    Returns
    -------
    local_path : str
        Path to downloaded file.
    """
    if not year:
        available_years = list_available_years(country)
        year = max(available_years)
        log.info(f"No year specified. Selected latest year available ({year}).")
    url = build_url(country, year)
    log.info(f"Downloading worldpop data from URL {url}.")
    local_path = download_from_ftp(url, output_dir, overwrite=overwrite)
    log.info(f"Downloaded worldpop data to {os.path.abspath(local_path)}.")
    return local_path


def _parse_worldpop_filename(filename):
    """Parse worldpop filename into a namedtuple."""
    WorldpopFile = namedtuple(
        "WorldpopFile", ["country", "datatype", "prefix", "year", "suffix", "filename"]
    )
    basename = filename.split(".")[0]
    if "UNadj" in basename:
        country, datatype, year, suffix = basename.split("_")
    else:
        country, datatype, year = basename.split("_")
        suffix = ""
    prefix = f"{country}_{datatype}"
    return WorldpopFile(country, datatype, prefix, int(year), suffix, filename)


def _clean_datadir(directory):
    """Check a directory for multiple Worldpop data files and keep only the
    latest one.
    """
    rasters = [f for f in os.listdir(directory) if f.lower().endswith(".tif")]
    if len(rasters) <= 1:
        log.info(f"Data directory does not require cleaning.")
        return

    # Make a summary of all years available for each prefix/suffix combination
    summary = {}
    datafiles = [_parse_worldpop_filename(f) for f in rasters]
    for datafile in datafiles:
        key = "__".join([datafile.prefix, datafile.suffix])
        if key not in summary:
            summary[key] = []
        summary[key].append(datafile.year)

    # Create a list of files to keep (one per prefix-suffix combination)
    to_keep = []
    for key, years in summary.items():
        prefix, suffix = key.split("__")
        latest = max(years)
        if suffix:
            to_keep.append(f"{prefix}_{latest}_{suffix}.tif")
        else:
            to_keep.append(f"{prefix}_{latest}.tif")

    for raster in rasters:
        if raster not in to_keep:
            log.info(f"Removing {raster} because a more recent version is available.")
            os.remove(os.path.join(directory, raster))
    return
