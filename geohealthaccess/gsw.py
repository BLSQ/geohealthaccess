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
import os
from tempfile import TemporaryDirectory

import geopandas as gpd
import requests
from loguru import logger
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from shapely.geometry import Polygon

from geohealthaccess import storage
from geohealthaccess.preprocessing import mask_raster, merge_tiles, reproject
from geohealthaccess.utils import download_from_url, size_from_url

logger.disable("__name__")


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
            latpol = "S"
        else:
            latpol = "N"
        if lon < 0:
            lonpol = "W"
        else:
            lonpol = "E"

        lat, lon = abs(lat), abs(lon)

        if lat % 10 != 0:
            lat = int(lat - lat % 10)
            if latpol == "N":
                lat += 10
        if lat == 0:
            latpol = "N"

        if lon % 10 != 0:
            lon = int(lon - lon % 10)
            if lonpol == "W":
                lon += 10
        if lon == 0:
            lonpol = "E"

        return f"{lon}{lonpol}_{lat}{latpol}"

    def spatial_index(self):
        """Build the spatial index."""
        geoms, names = [], []
        # Build a grid with 10 x 10 degrees cells
        for lon, lat in itertools.product(range(-180, 180, 10), range(-50, 90, 10)):
            geoms.append(
                Polygon(
                    (
                        (lon, lat),
                        (lon + 10, lat),
                        (lon + 10, lat - 10),
                        (lon, lat - 10),
                        (lon, lat),
                    )
                )
            )
            names.append(self.location_id(lat, lon))
        sindex = gpd.GeoDataFrame(index=names, geometry=geoms, crs=CRS.from_epsg(4326))
        logger.info(f"GSW tiles indexed ({len(sindex)} tiles).")
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
        logger.info(f"{len(tiles)} tiles are required to cover the area of interest.")
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


def preprocess(src_dir, dst_file, dst_crs, dst_res, geom, overwrite=False):
    """Preprocess SRTM elevation data.

    Creates a surface water raster from Global Surface Water tiles.
    Parameters
    ----------
    src_dir : str
        Path to directory where GSW tiles are stored.
    dst_file : str
        Path to output raster.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_res : int or float
        Target spatial resolution in `dst_crs` units.
    geom : shapely geometry
        Area of interest (EPSG:4326).
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    str
        Path to outptut raster.
    """
    if storage.exists(dst_file) and not overwrite:
        logger.info(
            f"{os.path.basename(dst_file)} already exists. Skipping processing."
        )
        return dst_file

    tiles = storage.glob(os.path.join(src_dir, "*.tif"))
    dst_bounds = transform_bounds(CRS.from_epsg(4326), dst_crs, *geom.bounds)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        # Make a local copy of all tiles
        for tile in tiles:
            storage.cp(tile, os.path.join(tmp_dir, os.path.basename(tile)))

        # Merge tiles if necessary
        tiles = storage.glob(os.path.join(tmp_dir, "*.tif"))
        if len(tiles) > 1:
            mosaic = merge_tiles(tiles, os.path.join(tmp_dir, "mosaic.tif"), nodata=255)
        else:
            mosaic = tiles[0]

        # Reproject
        dst_tmp = reproject(
            src_raster=mosaic,
            dst_raster=os.path.join(tmp_dir, "surface_water.tif"),
            dst_crs=dst_crs,
            dst_bounds=dst_bounds,
            dst_res=dst_res,
            src_nodata=255,
            dst_nodata=255,
            dst_dtype="Byte",
            resampling_method="max",
        )

        # Assign nodata to pixels outside boundaries
        dst_tmp = mask_raster(dst_tmp, geom)

        storage.cp(dst_tmp, dst_file)

    return dst_file
