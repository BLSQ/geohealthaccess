"""Search and download tiles from the Copernicus Global Land Cover product.

The module provides a `CGLC` class to search and download CGLC products based on
an input shapely geometry. It also contains helper functions to make sense of
CGLC files in a local directory.

Examples
--------
Downloading all CGLC tiles that intersect an area of interest `geom` into a
directory `output_dir`::

    cglc = CGLC()
    tiles = cglc.search(geom)
    for tile in tiles:
        cglc.download(tile, output_dir)

Notes
-----
See `<https://lcviewer.vito.be/about>`_ for more information about the CGLC project.
"""

import os
from collections import namedtuple

import geopandas as gpd
from loguru import logger
import requests
from requests_file import FileAdapter
from rasterio.crs import CRS
from shapely.geometry import Polygon

from geohealthaccess.utils import download_from_url, size_from_url


logger.disable("__name__")


def tile_id(url):
    """Extract tile ID from its URL.

    Returns
    -------
    str
        Tile ID.
    """
    basename = url.split("/")[-1]
    return basename.split("_")[0]


def tile_geom(id_):
    """Get tile geometry from its ID.

    Returns
    -------
    Polygon
        Shapely geometry of the tile.
    """
    xmin = int(id_[1:4])
    ymax = int(id_[5:7])
    if id_[0] == "W":
        xmin *= -1
    if id_[4] == "S":
        ymax *= -1
    ymin = ymax - 20
    xmax = xmin + 20
    coords = ((xmin, ymax), (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))
    return Polygon(coords)


class CGLC:
    """A catalog of all available CGLC tiles.

    Attributes
    ----------
    MANIFEST_URL : str
        URL to the manifest text file that is used to create the spatial index.
    """

    def __init__(self):
        """Initialize CGLC catalog."""
        self.MANIFEST_URL = (
            "https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/"
            "manifest_cgls_lc_v2_100m_global_2015.txt"
        )
        self.session = requests.Session()
        self.manifest = self.parse_manifest()
        self.sindex = self.spatial_index()

    def __repr__(self):
        return "geohealthaccess.cglc.CGLC()"

    def parse_manifest(self):
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
        logger.info(f"Parsing CGLC manifest from {self.MANIFEST_URL}.")
        r = self.session.get(self.MANIFEST_URL)
        r.raise_for_status()
        return r.text.splitlines()

    def spatial_index(self):
        """Build a spatial index from the Manifest text file.

        Returns
        -------
        geodataframe
            GeoDataFrame version of the catalog with tile IDs, URL and geometry.
        """
        sindex = gpd.GeoDataFrame(
            index=[tile_id(tile) for tile in self.manifest],
            data=self.manifest,
            columns=["url"],
            geometry=[tile_geom(tile_id(tile)) for tile in self.manifest],
            crs=CRS.from_epsg(4326),
        )
        logger.info(f"CGLC spatial index has been built ({len(sindex)} tiles).")
        return sindex

    def search(self, geom):
        """Search the CGLC tiles required to cover a given geometry.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest.

        Returns
        -------
        list of namedtuples
            Required CGLC tiles as namedtuples.
        """
        tiles = self.sindex[self.sindex.intersects(geom)].index
        logger.info(f"{len(tiles)} CGLC tiles required to cover the area of interest.")
        return list(tiles)

    def download(self, tile, output_dir, show_progress=True, overwrite=False):
        """Download a CGLC tile.

        Parameters
        ----------
        tile : str
            CGLC tile ID.
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
        url = self.sindex.url[tile]
        return download_from_url(
            self.session, url, output_dir, show_progress, overwrite
        )

    def download_size(self, tile):
        """Get download size of a tile.

        Parameters
        ----------
        tile : str
            CGLC tile ID.

        Returns
        -------
        int
            Size in bytes.
        """
        url = self.sindex.url[tile]
        return size_from_url(self.session, url)


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
    logger.info(f"Found {len(unique)} unique CGLC tiles.")
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
    logger.warning(f"Layer {name} not found.")
    return None
