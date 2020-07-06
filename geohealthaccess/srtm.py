"""Search and download SRTM tiles.

The module provides a `SRTM` class to search and download SRTM tiles from the
NASA EarthData server.

Examples
--------
Downloading SRTM tiles to cover the area of interest `geom` into `output_dir`::

    srtm = SRTM()
    srtm.authentify(username, password)
    tiles = srtm.search(geom)
    for tile in tiles:
        srtm.download(tile, output_dir)

Notes
-----
EarthData credentials are required. Registration [1]_ is free.

References
----------
.. [1] `NASA EarthData Register <https://urs.earthdata.nasa.gov/users/new>`_
"""

import logging

import geopandas as gpd
import requests
from bs4 import BeautifulSoup
from pkg_resources import resource_filename

from geohealthaccess.utils import download_from_url, size_from_url

log = logging.getLogger(__name__)


class SRTM:
    """Access SRTM data."""

    def __init__(self):
        """Initialize SRTM tiles index."""
        self.HOMEPAGE_URL = "https://urs.earthdata.nasa.gov"
        self.LOGIN_URL = "https://urs.earthdata.nasa.gov/login"
        self.PROFILE_URL = "https://urs.earthdata.nasa.gov/profile"
        self.DOWNLOAD_URL = (
            "https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/"
        )
        self.sindex = self.spatial_index()
        self.session = requests.Session()

    @property
    def authenticity_token(self):
        """Find authentiticy token in EarthData homepage as it is required to login.

        Returns
        -------
        token : str
            Authenticity token.
        """
        page = self.session.get(self.HOMEPAGE_URL).text
        soup = BeautifulSoup(page, "html.parser")
        token = ""
        for element in soup.find_all("input"):
            if element.attrs.get("name") == "authenticity_token":
                token = element.attrs.get("value")
        if not token:
            raise ValueError("Token not found in EarthData login page.")
        return token

    @property
    def logged_in(self):
        """Check if log-in to EarthData succeeded based on cookie values.

        Returns
        -------
        user_logged : bool
            `True` if the login was successfull.
        """
        response_cookies = self.session.cookies.get_dict()
        user_logged = response_cookies.get("urs_user_already_logged")
        return user_logged == "yes"

    def authentify(self, username, password):
        """Log-in to NASA EarthData platform.

        Parameters
        ----------
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
        r = self.session.get(self.HOMEPAGE_URL)
        r.raise_for_status()
        payload = {
            "username": username,
            "password": password,
            "authenticity_token": self.authenticity_token,
        }
        r = self.session.post(self.LOGIN_URL, data=payload)
        r.raise_for_status()
        if not self.logged_in:
            raise requests.exceptions.ConnectionError("Log-in to EarthData failed.")
        log.info(f"Successfully logged-in to EarthData with username `{username}`.")

    def spatial_index(self):
        """Load spatial index of SRTM tiles.

        Returns
        -------
        geodataframe
            SRTM tiles spatial index.
        """
        sindex = gpd.read_file(resource_filename(__name__, "resources/srtm.geojson"))
        log.info(f"SRTM spatial index loaded ({len(sindex)} tiles).")
        return sindex

    def search(self, geom):
        """List SRTM tiles required to cover the area of interest.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest as a shapely geometry.

        Returns
        -------
        list of str
            List of SRTM tile filenames.
        """
        tiles = self.sindex[self.sindex.intersects(geom)]
        log.info(f"{len(tiles)} SRTM tiles required to cover the area of interest.")
        return list(tiles.dataFile)

    def download(
        self, tile, output_dir, show_progress=True, overwrite=False, pbar_position=0
    ):
        """Download a SRTM tile.

        Parameters
        ----------
        tile : str
            Tile name.
        output_dir : str
            Path to output directory.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Force overwrite of existing file.
        pbar_position : bool, optional (default=0)
            Set the absolute position of the progress bar.

        Returns
        -------
        str
            Path to outptut file.
        """
        url = self.DOWNLOAD_URL + tile
        return download_from_url(
            self.session, url, output_dir, show_progress, overwrite, pbar_position
        )

    def download_size(self, tile):
        """Get download size of a SRTM tile.

        Parameters
        ----------
        tile : str
            Tile name.

        Returns
        -------
        int
            Size in bytes.
        """
        url = self.DOWNLOAD_URL + tile
        return size_from_url(self.session, url)
