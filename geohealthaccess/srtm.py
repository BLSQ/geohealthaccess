"""Download and preprocess elevation data from the SRTM."""

import logging

import geopandas as gpd
import requests
from bs4 import BeautifulSoup
from pkg_resources import resource_filename

from geohealthaccess.utils import download_from_url

log = logging.getLogger(__name__)

HOMEPAGE_URL = "https://urs.earthdata.nasa.gov"
LOGIN_URL = "https://urs.earthdata.nasa.gov/login"
PROFILE_URL = "https://urs.earthdata.nasa.gov/profile"
DOWNLOAD_URL = "http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/"


def required_tiles(geom):
    """List SRTM tiles required to cover the area of interest.

    Parameters
    ----------
    geom : shapely geometry
        The area of interest.

    Returns
    -------
    tiles : list
        List of the SRTM tiles (filenames) that intersects the area
        of interest.
    """
    tiles = gpd.read_file(resource_filename(__name__, "resources/srtm.geojson"))
    tiles = tiles[tiles.intersects(geom)]
    log.info(f"{len(tiles)} SRTM tiles required to cover the area of interest.")
    return list(tiles.dataFile)


def find_authenticity_token(login_page):
    """Find authentiticy token in EarthData homepage as it is required to login.

    Parameters
    ----------
    login_page : str
        HTML source code of the login page.

    Returns
    -------
    token : str
        Authenticity token.
    """
    soup = BeautifulSoup(login_page, "html.parser")
    token = ""
    for element in soup.find_all("input"):
        if element.attrs.get("name") == "authenticity_token":
            token = element.attrs.get("value")
    if not token:
        raise ValueError("Token not found in EarthData login page.")
    return token


def logged_in(login_response):
    """Check if log-in to EarthData succeeded based on cookie values.

    Parameters
    ----------
    login_response : request object
        Response to the login POST request.

    Returns
    -------
    user_logged : bool
        `True` if the login was successfull.
    """
    response_cookies = login_response.cookies.get_dict()
    user_logged = response_cookies.get("urs_user_already_logged")
    return user_logged == "yes"


def authentify(session, username, password):
    """Authentify a requests session by logging into NASA EarthData platform.

    Parameters
    ----------
    session : requests.Session()
        An initialized requests session object.
    username : str
        NASA EarthData username.
    password : str
        NASA EarthData password.

    Returns
    -------
    session : requests.Session()
        Updated requests session object with authentified cookies
        and headers.
    """
    r = session.get(HOMEPAGE_URL)
    r.raise_for_status()
    token = find_authenticity_token(r.text)
    payload = {"username": username, "password": password, "authenticity_token": token}
    r = session.post(LOGIN_URL, data=payload)
    r.raise_for_status()
    if not logged_in(r):
        raise requests.exceptions.ConnectionError("Log-in to EarthData failed.")
    log.info(f"Successfully logged-in to EarthData with username <{username}>.")
    return session


def _expected_filename(tile_name):
    """Get expected filename of a given tile after decompression."""
    return tile_name.split(".")[0] + ".hgt"


def download(geom, output_dir, username, password, show_progress=True, overwrite=False):
    """Download the SRTM tiles that intersects the area of interest.

    Parameters
    ----------
    geom : shapely geometry
        Area of interest.
    output_dir : str
        Output directory where SRTM tiles will be downloaded.
    username : str
        NASA EarthData username.
    password : str
        NASA EarthData password.
    show_progress : bool, optional (default=True)
        Show progress bars.
    overwrite : bool, optional (default=False)
        Overwrite existing files.

    Returns
    -------
    tiles : list of str
        List of downloaded SRTM tiles.
    """
    tiles = required_tiles(geom)
    with requests.Session() as session:
        authentify(session, username, password)
        for tile in tiles:
            url = DOWNLOAD_URL + tile
            download_from_url(
                session, url, output_dir, show_progress, overwrite=overwrite
            )
    return tiles
