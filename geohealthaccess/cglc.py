"""Search and download tiles from the Copernicus Global Land Cover product.

The module provides a `Tile` and a `Catalog` classes to search and download CGLC
products based on an input shapely geometry. It also contains helper functions to
make sense of CGLC files in a local directory.


Examples
--------
Building the catalog::

    from geohealthaccess import cglc
    catalog = cglc.Catalog()

Searching for tiles intersecting an area of interest::

    tiles = catalog.search(area_of_interest)
    for tile in tiles:
        print(tile.id_)

Downloading tiles::

    for tile in tiles:
        tile.download(output_dir)

Notes
-----
See `<https://lcviewer.vito.be/>`_ for more information.

Attributes
----------
CGLC_MANIFEST : str
    A manifest text file keeps track of the URLs of all available CGLC tiles. This
    is the default URL if none is provided by the user when building the catalog.
"""


import logging
import os
from collections import namedtuple

import geopandas as gpd
import requests
from requests_file import FileAdapter
from rasterio.crs import CRS
from shapely.geometry import Polygon

from geohealthaccess.utils import download_from_url

log = logging.getLogger(__name__)

# A manifest text file keeps track of all the URLs of the available tiles
CGLC_MANIFEST = (
    "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/"
    "manifest_cgls_lc_v2_100m_global_2015.txt"
)


class Tile:
    """A single CGLC tile."""

    def __init__(self, url):
        """Initialize a CGLC tile.

        Parameters
        ----------
        url : str
            URL of the tile.
        """
        self.url = url

    def __repr__(self):
        return f'Tile(id="{self.id_}")'

    @property
    def id_(self):
        """Tile ID extracted from its URL.

        Returns
        -------
        str
            Tile ID.
        """
        basename = self.url.split("/")[-1]
        return basename.split("_")[0]

    @property
    def geom(self):
        """Tile geometry as a shapely polygon."""
        xmin = int(self.id_[1:4])
        ymax = int(self.id_[5:7])
        if self.id_[0] == "W":
            xmin *= -1
        if self.id_[4] == "S":
            ymax *= -1
        ymin = ymax - 20
        xmax = xmin + 20
        coords = ((xmin, ymax), (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))
        return Polygon(coords)

    def download(self, dst_dir, show_progress=True, overwrite=False):
        """Download the CGLC tile.

        Parameters
        ----------
        dst_dir : str
            Path to output directory. Filename will be guessed from the URL.
        show_progress : bool, optional
            Show the download progress bar.
        overwrite : bool, optional
            Force overwrite of existing data.

        Returns
        -------
        fname : str
            Local path to downloaded file.
        """
        with requests.Session() as s:
            fname = download_from_url(
                s, self.url, dst_dir, show_progress=show_progress, overwrite=overwrite
            )
        return fname


class Catalog:
    """A catalog of all available CGLC tiles."""

    def __init__(self, url=None):
        """Initialize catalog.

        Parameters
        ----------
        url : str, optional
            URL to the CGLC manifest text file. A default one is provided.
        """
        self.url = url
        if self.url is None:
            self.url = CGLC_MANIFEST
        self.tiles = self.build()
        log.info(f"CGLC catalog has been built ({len(self.tiles)} tiles).")

    def __repr__(self):
        return f'Catalog(url="{self.url}")'

    @staticmethod
    def parse_manifest(url):
        """Parse manifest text file.

        Parameters
        ----------
        url : str
            URL of the manifest.

        Returns
        -------
        list of tiles
            A list of all the available CGLC tiles as ``Tile()`` objects.

        Raises
        ------
        HTTPError
            If connection to manifest URL is not sucessfull.
        """
        log.info(f"Parsing CGLC manifest from {url}.")
        s = requests.Session()
        s.mount("file://", FileAdapter())
        r = s.get(url)
        r.raise_for_status()
        return [Tile(url) for url in r.text.split("\r\n") if url]

    def build(self):
        """Build the catalog from the Manifest text file.

        Returns
        -------
        geodataframe
            GeoDataFrame version of the catalog with tile IDs, URL and geometry.
        """
        tiles = self.parse_manifest(self.url)
        return gpd.GeoDataFrame(
            index=[tile.id_ for tile in tiles],
            data=[tile.url for tile in tiles],
            columns=["url"],
            geometry=[tile.geom for tile in tiles],
            crs=CRS.from_epsg(4326),
        )

    def search(self, geom):
        """Search the CGLC tiles required to cover a given geometry.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest.

        Returns
        -------
        list of tiles
            Required CGLC tiles as ``Tile`` objects.
        """
        required = self.tiles[self.tiles.intersects(geom)]
        log.info(f"Found {len(required)} CGLC tiles.")
        return list(required.url.apply(Tile))


def parse_filename(path):
    """Parse a CGLC filename.

    Parameters
    ----------
    path : str
        Path to CGLC file.

    Returns
    -------
    layer : namedtuple
        Parsed filename as a namedtuple.
    """
    fname = os.path.basename(path)
    parts = fname.split("_")
    if len(parts) != 8:
        raise ValueError("Not a CGLC file.")
    if not fname.lower().endswith(".tif"):
        raise ValueError("Not a GeoTIFF file.")

    parts = fname.split("_")
    Layer = namedtuple("Layer", ["path", "name", "tile", "epoch", "version"])
    return Layer(
        path=os.path.abspath(path),
        name=parts[6],
        tile=parts[0],
        epoch=int(parts[3][-4:]),
        version=parts[5],
    )


def _is_cglc(fname):
    """Check if a filename can be a CGLC raster."""
    if len(fname.split("_")) != 8:
        return False
    if not fname.lower().endswith(".tif") or "_ProbaV_LC100_" not in fname:
        return False
    return True


def unique_tiles(directory):
    """List unique CGLC tiles in a local directory.

    Parameters
    ----------
    directory : str
        Path to directory with CGLC files.

    Returns
    -------
    list of str
        List of unique tile IDs.
    """
    files = [f for f in os.listdir(directory) if _is_cglc(f)]
    tiles = [f.split("_")[0] for f in files]
    unique = list(set(tiles))
    log.info(f"Found {len(unique)} unique CGLC tiles.")
    return unique


def list_layers(directory, tile):
    """List available layers for a given tile ID.

    Parameters
    ----------
    directory : str
        Directory with CGLC files.
    tile : str
        Tile ID.

    Returns
    -------
    list of str
        List of layer names.
    """
    files = [f for f in os.listdir(directory) if _is_cglc(f) and f.startswith(tile)]
    return [f.split("_")[6] for f in files]


def find_layer(directory, tile, name):
    """Find a CGLC layer in a local directory.

    Parameters
    ----------
    directory : str
        Path to directory with CGLC files.
    tile : str
        Tile ID.
    name : str
        Layer name (e.g. ``grass-coverfraction-layer`` or ``discrete-classification``).

    Returns
    -------
    str
        Path to CGLC layer.
    """
    files = [f for f in os.listdir(directory) if _is_cglc(f)]
    for f in files:
        if f.startswith(tile) and f.split("_")[6] == name:
            return os.path.join(directory, f)
    log.warning(f"Layer {name} not found.")
    return None
