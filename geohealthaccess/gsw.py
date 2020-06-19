"""Search and download tiles from the Global Surface Water dataset.

The module provides a `GSW` classe to search and download GSW products based on
an input shapely geometry.

Examples
--------
Downloading GSW occurrence tiles that intersect an area of interest `geom` into
a directory `output_dir`::

    gsw = GSW()
    tiles = gsw.search(geom)
    for tile in tiles:
        gsw.download(tile, "occurrence", output_dir)

Notes
-----
See `<https://global-surface-water.appspot.com>`_ for more information about the
Global Surface Water [1] project.

References
----------
.. [1] Jean-Francois Pekel, Andrew Cottam, Noel Gorelick, Alan S. Belward.
   High-resolution mapping of global surface water and its long-term changes.
   Nature 540, 418-422 (2016) [DOI: 10.1038/nature20584].
"""

import itertools
import logging

import geopandas as gpd
import requests
from requests_file import FileAdapter
from rasterio.crs import CRS
from shapely.geometry import Polygon

from geohealthaccess.utils import download_from_url, size_from_url


log = logging.getLogger(__name__)


class GSW:
    """Global Surface Water tile index."""

    def __init__(self):
        self.BASEURL = "https://storage.googleapis.com/global-surface-water/downloads2"
        self.VERSION = "1_1"
        self.PRODUCTS = [
            "occurrence",
            "change",
            "seasonality",
            "recurrence",
            "transitions",
            "extent",
        ]
        self.session = requests.Session()
        self.session.mount("file://", FileAdapter())
        self.sindex = self.spatial_index()

    def __repr__(self):
        return "geohealthaccess.gsw.GSW()"

    def _checkproduct(self, product):
        """Raise an error if GSW product is invalid."""
        if product not in self.PRODUCTS:
            raise ValueError(f"`{product}` is not a valid GSW product name.")

    @staticmethod
    def location_id(lat, lon):
        """Generate GSW location ID from lat/lon coordinates.

        Parameters
        ----------
        lat : float
            Decimal latitude.
        lon : float
            Decimal longitude.

        Returns
        -------
        str
            GSW location ID.

        Notes
        -----
        GSW tiles are organized according to a 10° x 10° grid. The location ID of a tile
        is a string representation of its top-left coordinates, e.g.: `0E_50N` or
        `50W_20S`.
        """
        if lat < 0:
            lat = abs(lat)
            lat = f"{int(lat - lat % 10)}S"
        else:
            lat = f"{int(lat - lat % 10 + 10)}N"
        if lon < 0:
            lon = abs(lon)
            lon = f"{int(lon - lon % 10 + 10)}W"
        else:
            lon = f"{int(lon - lon % 10)}E"
        return f"{lon}_{lat}"

    def spatial_index(self):
        """Build the spatial index."""
        geoms, names = [], []
        # Build a grid with 10 x 10 degrees cells
        for lon, lat in itertools.product(range(-180, 180, 10), range(-90, 90, 10)):
            geoms.append(
                Polygon(
                    (
                        (lon, lat + 10),
                        (lon, lat),
                        (lon + 10, lat),
                        (lon + 10, lat + 10),
                        (lon, lat + 10),
                    )
                )
            )
            names.append(self.location_id(lat, lon))
        sindex = gpd.GeoDataFrame(index=names, geometry=geoms, crs=CRS.from_epsg(4326))
        log.info(f"GSW tiles indexed ({len(sindex)} tiles).")
        return sindex

    def search(self, geom):
        """List the tiles required to cover the area of interest.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest (WGS84).

        Returns
        -------
        list of tiles
            List of required GSW tiles.
        """
        tiles = self.sindex[self.sindex.intersects(geom)]
        log.info(f"{len(tiles)} tiles are required to cover the area of interest.")
        return list(tiles.index)

    def url(self, tile, product):
        """Get download URL of a GSW tile.

        Parameters
        ----------
        tile : str
            GSW tile location id.
        product : str
            GSW product type.

        Returns
        -------
        str
            Download URL.
        """
        self._checkproduct(product)
        return f"{self.BASEURL}/{product}/{product}_{tile}_v{self.VERSION}.tif"

    def download(self, tile, product, output_dir, show_progress=True, overwrite=False):
        """Download a GSW tile.

        Parameters
        ----------
        tile : str
            GSW tile location id.
        product : str
            GSW product type.
        output_dir : str
            Path to output directory.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Force overwrite of existing files.

        Returns
        -------
        str
            Path to output file.
        """
        url = self.url(tile, product)
        return download_from_url(
            self.session, url, output_dir, show_progress, overwrite
        )

    def download_size(self, tile, product):
        """Get download size of a GSW tile.

        Parameters
        ----------
        tile : str
            GSW tile location id.
        product : str
            GSW product type.

        Returns
        -------
        int
            Size in bytes.
        """
        url = self.url(tile, product)
        return size_from_url(self.session, url)
