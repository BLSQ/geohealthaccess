import os
from tempfile import TemporaryDirectory

import numpy as np
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
import requests
from loguru import logger

from geohealthaccess import storage
from geohealthaccess.preprocessing import merge_tiles, reproject, mask_raster
from geohealthaccess.utils import download_from_url, size_from_url

logger.disable("__name__")


class CGLC:
    """Access Copernicus Global Land Cover data.

    Attributes
    ----------
    BASE_URL : str
        Base URL where tiles can be downloaded.
    VERSION : str
        Dataset version.
    DATASETS : dict
        Available datasets and epochs.
    LABELS : list
        Land cover labels.
    """

    def __init__(self):
        """Initialize CGLC catalog."""
        self.BASE_URL = "https://s3-eu-west-1.amazonaws.com/vito.landcover.global"
        self.VERSION = "v3.0.1"
        self.DATASETS = {
            2015: "2015-base",
            2016: "2016-conso",
            2017: "2017-conso",
            2018: "2018-conso",
            2019: "2019-nrt",
        }
        self.LABELS = [
            "Bare",
            "BuiltUp",
            "Crops",
            "Tree",
            "Grass",
            "MossLichen",
            "SeasonalWater",
            "Shrub",
            "Snow",
            "PermanentWater",
        ]
        self.session = requests.Session()

    def download_url(self, tile, label, year=2019):
        """Build download URL of a cover fraction land cover tile.

        Parameters
        ----------
        tile : str
            Tile name (e.g. E020N60).
        label : str
            Land cover label.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.

        Returns
        -------
        url : str
            Path to remote GeoTIFF.

        Raises
        ------
        ValueError
            If year or land cover class are unavailable.
        """
        if year not in self.DATASETS:
            raise ValueError("Year unavailable.")
        if label not in self.LABELS:
            raise ValueError("Land cover class unavailable.")
        fname = f"{tile}_PROBAV_LC100_global_{self.VERSION}_{self.DATASETS[year]}"
        fname += f"_{label}-CoverFraction-layer_EPSG-4326.tif"
        return "/".join((self.BASE_URL, self.VERSION, str(year), tile, fname))

    @staticmethod
    def format_lat(lat):
        """Format decimal lontitude into a string.

        Parameters
        ----------
        lat : int
            Decimal latitude.

        Returns
        -------
        str
            Formatted latitude string.

        Examples
        --------
        >>> format_lat(-20)
        'S20'
        """
        if lat < 0:
            ns = "S"
            lat *= -1
        else:
            ns = "N"
        return ns + str(int(lat)).zfill(2)

    @staticmethod
    def format_lon(lon):
        """Format decimal longitude into a string.

        Parameters
        ----------
        lon : int
            Decimal longitude.

        Returns
        -------
        str
            Formatted longitude string.

        Examples
        --------
        >>> format_lon(-60)
        'W060'
        """
        if lon < 0:
            ew = "W"
            lon *= -1
        else:
            ew = "E"
        return ew + str(int(lon)).zfill(3)

    def format_latlon(self, lat, lon):
        """Format decimal latitude and longitude into a string.

        Parameters
        ----------
        lat : int
            Decimal latitude.
        lon : int
            Decimal longitude.

        Returns
        -------
        str
            Formatted latitude and longitude string.

        Examples
        --------
        >>> format_latlon(-30, 40)
        'E040S30'
        """
        return self.format_lon(lon) + self.format_lat(lat)

    def search(self, geom):
        """Get name of tiles that intersects a geometry.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest.

        Returns
        -------
        tiles : list of str
            Names of the intersecting tiles.
        """
        tiles = []
        min_lon, min_lat, max_lon, max_lat = geom.bounds
        lon_stops = [
            lon // 20 * 20
            for lon in np.append(np.arange(min_lon, max_lon, 20), max_lon)
        ]
        lat_stops = [
            lat // 20 * 20 + 20
            for lat in np.append(np.arange(min_lat, max_lat, 20), max_lat)
        ]
        for lon in lon_stops:
            for lat in lat_stops:
                tile_id = self.format_latlon(lat, lon)
                if tile_id not in tiles:
                    tiles.append(tile_id)
        logger.info(f"{len(tiles)} tiles required to cover the input geometry.")
        return tiles

    def download(
        self, tile, label, output_dir, year=2019, show_progress=True, overwrite=False
    ):
        """Download a CGLC tile.

        Parameters
        ----------
        tile : str
            Tile name (e.g. E020N60).
        label : str
            Land cover label.
        output_dir : str
            Path to output directory.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Force overwrite of existing files.

        Returns
        -------
        str
            Path to output file.
        """
        url = self.download_url(tile, label, year)
        return download_from_url(
            self.session, url, output_dir, show_progress, overwrite
        )

    def download_all(
        self, tile, output_dir, year=2019, show_progress=True, overwrite=False
    ):
        """Download all land cover layers in a tile.

        Parameters
        ----------
        tile : str
            Tile name (e.g. E020N60).
        output_dir : str
            Path to output directory.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Force overwrite of existing files.

        Returns
        -------
        list of str
            List of output files.
        """
        files = []
        os.makedirs(output_dir, exist_ok=True)
        for label in self.LABELS:
            files.append(
                self.download(tile, label, output_dir, year, show_progress, overwrite)
            )
        return files

    def download_size(self, tile, label, year=2019):
        """Get download size of a tile.

        Parameters
        ----------
        tile : str
            Tile name (e.g. E020N60).
        label : str
            Land cover label.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.

        Returns
        -------
        int
            Size in bytes.
        """
        url = self.download_url(tile, label, year)
        return size_from_url(self.session, url)


def preprocess(input_dir, dst_dir, geom, crs, res, overwrite=False):
    """Process land cover tiles into a new grid.

    Raw land cover tiles are merged and reprojected to the grid identified
    by `crs`, `geom` and `res`. Data outside `geom` are assigned
    NaN values.

    Parameters
    ----------
    input_dir : str
        Path to directory where land cover tiles are stored.
    dst_dir : str
        Path to output directory.
    geom : shapely geometry, optional
        Area of interest. Used to create a nodata mask.
    crs : CRS
        Target CRS.
    res : int or float
        Target spatial resolution in `crs` units.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    str
        Path to output directory.
    """
    bounds = transform_bounds(CRS.from_epsg(4326), crs, *geom.bounds)
    lc = CGLC()
    for label in lc.LABELS:
        dst_file = os.path.join(dst_dir, f"{label}.tif")
        if storage.exists(dst_file) and not overwrite:
            logger.info(f"Land cover {label} already preprocessed. Skipping.")
            return dst_dir
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            tmp_f = os.path.join(tmp_dir, f"{label}_merged.tif")
            tiles = storage.glob(os.path.join(input_dir, f"*LC100*{label}*.tif"))
            merged_tiles = merge_tiles(tiles, tmp_f, nodata=255)
            tmp_f = os.path.join(tmp_dir, f"{label}_reproj.tif")
            reproj = reproject(
                merged_tiles,
                tmp_f,
                dst_crs=crs,
                dst_bounds=bounds,
                dst_res=res,
                dst_nodata=-9999,
                dst_dtype="Float32",
                resampling_method="bilinear",
                overwrite=overwrite,
            )
            if geom:
                masked = mask_raster(reproj, geom)
            storage.cp(masked, os.path.join(dst_dir, f"{label}.tif"))
    return dst_dir
