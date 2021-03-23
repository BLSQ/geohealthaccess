"""Download WorldPop population count datasets.

Notes
-----
See `<https://www.worldpop.org/>`_ for more information about the WorldPop project.
"""


from loguru import logger
import requests

from geohealthaccess import storage
from geohealthaccess.utils import download_from_url, size_from_url
from pkg_resources import parse_requirements


logger.disable("__name__")


BASE_URL = "https://data.worldpop.org/GIS/Population/Global_2000_2020"


def build_url(country, year=2020, un_adj=False):
    """Build download URL.

    Parameters
    ----------
    country : str
        Country ISO A3 code.
    year : int, optional
        Year of interest (2000--2020). Default=2020.
    un_adj : bool, optional
        Use UN adjusted population counts. Default=False.

    Returns
    -------
    url : str
        Download URL.
    """
    return (
        f"{BASE_URL}/{year}/{country.upper()}/"
        f"{country.lower()}_ppp_{year}{'_UNadj' if un_adj else ''}.tif"
    )


def download(
    country, output_dir, year=2020, un_adj=False, show_progress=True, overwrite=False
):
    """Download a WorldPop population dataset.

    Parameters
    ----------
    country : str
        Country ISO A3 code.
    output_dir : str
        Path to output directory.
    year : int, optional
        Year of interest (2000--2020). Default=2020.
    un_adj : bool, optional
        Use UN adjusted population counts. Default=False.
    show_progress : bool, optional
        Show progress bar. Default=False.
    overwrite : bool, optional
        Overwrite existing files. Default=True.

    Returns
    -------
    str
        Path to output GeoTIFF file.
    """
    url = build_url(country, year=year, un_adj=un_adj)
    logger.info(f"Downloading population counts from {url}.")
    with requests.Session() as s:
        fp = download_from_url(
            s, url, output_dir, show_progress=show_progress, overwrite=overwrite
        )
    return fp
