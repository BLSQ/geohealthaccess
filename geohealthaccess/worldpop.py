"""Download WorldPop population datasets.

The module provides a `WorldPop` class to access WorldPop population datasets for
a given country and year.

Examples
--------
Downloading 2012 WorldPop population dataset of Burundi into `output_dir`::

    wpop = WorldPop()
    wpop.login()
    wpop.download("BDI", 2012, output_dir)
    wpop.logout()

Notes
-----
See `<https://www.worldpop.org/>`_ for more information about the WorldPop project.
"""

import os
from collections import namedtuple
from ftplib import FTP, error_reply

from loguru import logger

from geohealthaccess import storage
from geohealthaccess.utils import download_from_ftp, size_from_ftp


logger.disable("__name__")


class WorldPop:
    """Access WorldPop population datasets.

    Attributes
    ----------
    FTP_HOST : str
        Hostname of the WorldPop FTP server.
    BASE_DIR : str
        Base directory where country population datasets are located.
    """

    def __init__(self):
        """Initialize a simple WorldPop API."""
        self.FTP_HOST = "ftp.worldpop.org.uk"
        self.BASE_DIR = "GIS/Population/Global_2000_2020"
        self.ftp = None

    def login(self):
        """Login to FTP server."""
        self.ftp = FTP(self.FTP_HOST)
        self.ftp.login()
        if self.ftp.lastresp != "230":
            raise error_reply("FTP login error.")

    def logout(self):
        """Logout from FTP server and close connection."""
        self.ftp.quit()

    def available_years(self):
        """List available epochs.

        Returns
        -------
        list of int
            Available years.
        """
        years = []
        listdir = self.ftp.nlst(self.BASE_DIR)
        for path in listdir:
            fname = path.split("/")[-1]
            if fname.isnumeric() and len(fname) == 4:
                years.append(int(fname))
        return years

    def url(self, country, year):
        """Build download URL for a worldpop population dataset.

        Parameters
        ----------
        country : str
            Country ISO A3 code (example: `COD`).
        year : int
            Year of interest.

        Returns
        -------
        str
            Download URL.
        """
        directory = f"{self.BASE_DIR}/{year}/{country.upper()}"
        filename = f"{country.lower()}_ppp_{year}.tif"
        return f"ftp://{self.FTP_HOST}/{directory}/{filename}"

    def download(self, country, output_dir, year=None, overwrite=False):
        """Download a worldpop population dataset.

        Parameters
        ----------
        country : str
            Country ISO A3 code (example: `COD`).
        output_dir : str
            Path to output directory.
        year : int, optional
            Year of interest (>= 2000). If not specified, latest year available
            is used.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Force overwrite of existing data.

        Returns
        -------
        str
            Path to downloaded file.
        """
        if not year:
            year = max(self.available_years())
            logger.info(f"No year specified. Selected latest year available ({year}).")
        url = self.url(country, year)
        file_path = download_from_ftp(
            self.ftp, url, output_dir, show_progress=True, overwrite=overwrite
        )
        return file_path

    def download_size(self, country, year):
        """Get download size of a worldpop population dataset.

        Parameters
        ----------
        country : str
            Country ISO A3 code (example: `COD`).
        year : int, optional
            Year of interest (>= 2000). If not specified, latest year available
            is used.

        Returns
        -------
        int
            Size in bytes.
        """
        url = self.url(country, year)
        return size_from_ftp(self.ftp, url)


def parse_filename(filename):
    """Parse a worldpop filename.

    Parameters
    ----------
    filename : str
        WorldPop file name to parse.

    Returns
    -------
    namedtuple
        Parsed filename.
    """
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


def clean_datadir(directory):
    """Clean a directory containing WorldPop data files.

    The function ensures that only the latest datafile (i.e. the latest year) is
    kept for each country and product type. Older files will be removed.

    Parameters
    ----------
    directory : str
        Path to directory to check.
    """
    rasters = [f for f in storage.ls(directory) if f.lower().endswith(".tif")]
    if len(rasters) <= 1:
        logger.info("Data directory does not require cleaning.")
        return

    # Make a summary of all years available for each prefix/suffix combination
    summary = {}
    datafiles = [parse_filename(f) for f in rasters]
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
            logger.info(
                f"Removing {raster} because a more recent version is available."
            )
            storage.rm(os.path.join(directory, raster))
    return
