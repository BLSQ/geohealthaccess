import os
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
import requests
from loguru import logger
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from tqdm import tqdm

from geohealthaccess import storage
from geohealthaccess.preprocessing import mask_raster, reproject

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

    def download(self, geom, label, dst_file, year=2019, overwrite=False):
        """Download data from a single or multiple CGLC tiles.

        CGLC tiles are hosted as Cloud Optimized GeoTIFFs, allowing us to avoid
        downloading data outside of `geom`.

        Notes
        -----
        The function supports S3 or GCS URLs for `dst_file`.

        Parameters
        ----------
        geom : shapely geometry
            Data outside the boundaries of `geom` will not be downloaded.
        label : str
            Land cover label.
        dst_file : str
            Path to output raster.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.
        overwrite : bool, optional
            Force overwrite of existing files.

        Returns
        -------
        str
            Path to output GeoTIFF.
        """
        if storage.exists(dst_file) and not overwrite:
            if overwrite:
                logger.info(f"Removing old {os.path.basename(dst_file)} file.")
                storage.rm(dst_file)
            else:
                logger.info(
                    f"{os.path.basename(dst_file)} already exists. Skipping download."
                )
                return dst_file

        tiles = self.search(geom)
        for i, tile in enumerate(tiles):
            url = self.download_url(tile, label, year)
            with rasterio.open(url) as src:
                profile = src.profile
                win = src.window(*geom.bounds)
                win = win.round_offsets(op="floor")
                win = win.round_shape(op="ceil")
                transform = rasterio.windows.transform(win, src.transform)
                if i == 0:
                    shape = (len(tiles), win.height, win.width)
                    data = np.empty(shape, dtype=np.uint8)
                data[i, :, :] = src.read(
                    1, masked=True, boundless=True, window=win
                ).astype(np.uint8)

        # merge tiles
        # we temporarily use -1 as nodata value to make sure
        # the 255 value is ignored in the max operation
        data = data.astype(np.int16)
        data[data == 255] = -1
        mosaic = np.max(data, axis=0)
        mosaic[mosaic == -1] = 255
        mosaic = mosaic.astype(np.uint8)

        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            dst_file_tmp = os.path.join(tmp_dir, "cglc.tif")
            profile.update(
                transform=transform, height=data.shape[1], width=data.shape[2]
            )
            with rasterio.open(dst_file_tmp, "w", **profile) as dst:
                dst.write(mosaic, 1)
            storage.cp(dst_file_tmp, dst_file)

        return dst_file

    def download_all(
        self, geom, output_dir, year=2019, show_progress=True, overwrite=False
    ):
        """Download all land cover layers for a given geometry.

        Parameters
        ----------
        tile : str
            Tile name (e.g. E020N60).
        geom : shapely geometry
            Area of interest.
        output_dir : str
            Path to output directory.
        year : int, optional
            Epoch (between 2015 and 2019). Default=2019.
        show_progress : bool, optional
            Show progress bar.
        overwrite : bool, optional
            Force overwrite of existing files.

        Returns
        -------
        list of str
            List of output files.
        """
        files = []
        storage.mkdir(output_dir)

        if show_progress:
            pbar = tqdm(total=len(self.LABELS), desc="land cover")

        for label in self.LABELS:
            logger.info(f"Downloading `{label}` land cover data.")
            dst_file = os.path.join(output_dir, f"landcover_{label}.tif")
            files.append(self.download(geom, label, dst_file, year, overwrite))
            if show_progress:
                pbar.update(1)

        pbar.close()
        return files


def preprocess(src_dir, dst_dir, geom, crs, res, overwrite=False):
    """Process land cover tiles into a new grid.

    Raw land cover tiles are merged and reprojected to the grid identified
    by `crs`, `geom` and `res`. Data outside `geom` are assigned
    NaN values.

    Parameters
    ----------
    src_dir : str
        Path to directory where land cover tiles are stored.
    dst_dir : str
        Path to output directory.
    geom : shapely geometry
        Area of interest. Used to create a nodata mask.
    crs : CRS
        Target CRS.
    res : int or float
        Target spatial resolution in `crs` units.
    overwrite : bool, optional
        Overwrite existing files. Default=False.

    Returns
    -------
    str
        Path to output directory.
    """
    bounds = transform_bounds(CRS.from_epsg(4326), crs, *geom.bounds)
    lc = CGLC()
    for label in lc.LABELS:
        src_file = os.path.join(src_dir, f"landcover_{label}.tif")
        dst_file = os.path.join(dst_dir, f"landcover_{label}.tif")
        if storage.exists(dst_file) and not overwrite:
            logger.info(f"Land cover {label} already preprocessed. Skipping.")
            continue
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            src_file_tmp = os.path.join(tmp_dir, f"landcover_{label}.tif")
            storage.cp(src_file, src_file_tmp)
            dst_file_tmp = os.path.join(tmp_dir, f"landcover_{label}_reproj.tif")
            dst_file_tmp = reproject(
                src_file_tmp,
                dst_file_tmp,
                dst_crs=crs,
                dst_bounds=bounds,
                dst_res=res,
                src_nodata=255,
                dst_nodata=-9999,
                dst_dtype="Float32",
                resampling_method="bilinear",
                overwrite=overwrite,
            )
            mask_raster(dst_file_tmp, geom)
            storage.cp(dst_file_tmp, dst_file)
    return dst_dir
