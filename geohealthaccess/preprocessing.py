"""Preprocessing of input data."""

import os
import shutil
import subprocess
from tempfile import TemporaryDirectory

from loguru import logger
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import aligned_target, transform_bounds, transform_geom


logger.disable(__name__)


# Default GDAL creation options
# NB: PREDICTOR=3 is better for floating point data
GDAL_CO = [
    "TILED=YES",
    "BLOCKXSIZE=256",
    "BLOCKYSIZE=256",
    "COMPRESS=DEFLATE",
    "NUM_THREADS=ALL_CPUS",
    "PREDICTOR=2",
    "ZLEVEL=6",
]

# GDAL data types supported for the GeoTIFF driver
GDAL_DTYPES = [
    "Byte",
    "UInt16",
    "Int16",
    "UInt32",
    "Int32",
    "Float32",
    "Float64",
    "CInt16",
    "CInt32",
    "CFloat32",
    "CFloat64",
]


def default_compression(dtype):
    """Get default GeoTIFF compression options according to data type.

    Uses `DEFLATE` as the default compression algorithm, with `ZLEVEL=6` and
    `PREDICTOR=2`. Set `PREDICTOR=3` for floating point data. Set
    `NUM_THREADS=ALL_CPUS` to provide multi-threaded compression.

    Parameters
    ----------
    dtype : np.dtype or str
        Raster data type.

    Returns
    -------
    dict
        GeoTIFF driver compression options.
    """
    options = {
        "compress": "deflate",
        "predictor": 2,
        "zlevel": 6,
        "num_threads": "all_cpus",
    }
    if isinstance(dtype, str):
        dtype = np.dtype(dtype)
    if np.issubdtype(dtype, np.floating):
        options.update(predictor=3)
    return options


def default_tiling():
    """Return default tiling options for GeoTIFF driver.

    Returns
    -------
    dict
        GeoTIFF driver tiling options.
    """
    return {"tiled": True, "blockxsize": 256, "blockysize": 256}


def create_grid(geom, dst_crs, dst_res):
    """Create a raster grid for a given area of interest.

    Parameters
    ----------
    geom : shapely geometry
        Area of interest.
    dst_crs : CRS
        Target CRS as a rasterio CRS object.
    dst_res : int or float
        Spatial resolution (in `dst_crs` units).

    Returns
    -------
    transform: Affine
        Output affine transform object.
    shape : tuple of int
        Output shape (height, width).
    bounds : tuple of float
        Output bounds.
    """
    bounds = transform_bounds(CRS.from_epsg(4326), dst_crs, *geom.bounds)
    xmin, ymin, xmax, ymax = bounds
    transform = from_origin(xmin, ymax, dst_res, dst_res)
    ncols = (xmax - xmin) / dst_res
    nrows = (ymax - ymin) / dst_res
    transform, ncols, nrows = aligned_target(transform, ncols, nrows, dst_res)
    logger.info(f"Created raster grid of shape ({nrows}, {ncols}).")
    return transform, (nrows, ncols), bounds


def merge_tiles(src_files, dst_file, nodata=-1):
    """Merge multiple raster tiles into a single raster.

    The functions wraps the `gdal_merge.py` command-line script. Input raster tiles
    must share the same CRS and spatial resolution.

    Note
    ----
    See `documentation <https://gdal.org/programs/gdal_merge.html>`_.

    Parameters
    ----------
    src_files : list of str
        Paths to raster tiles.
    dst_file : str
        Path to output raster.
    nodata : float, optional
        Nodata value of the output raster.

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info(f"Merging {len(src_files)} raster tiles.")
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        vrt = os.path.join(tmpdir, "mosaic.vrt")
        command = ["gdalbuildvrt", "-oo", "NUM_THREADS=ALL_CPUS", vrt] + src_files
        logger.info(f"Running command `{' '.join(command)}`.")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

        command = ["gdal_translate", "-of", "GTiff", "-a_nodata", str(nodata)]
        # Add GDAL creation options for GeoTIFF format
        for creation_opt in GDAL_CO:
            command += ["-co", creation_opt]
        command += [vrt, dst_file]
        logger.info(f"Running command `{' '.join(command)}`.")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

    logger.info(f"Merged {len(src_files)} tiles into {os.path.basename(dst_file)}.")
    return dst_file


def reproject(
    src_raster,
    dst_raster,
    dst_crs,
    dst_bounds,
    dst_res,
    src_nodata=None,
    dst_nodata=None,
    dst_dtype=None,
    resampling_method="near",
    overwrite=False,
):
    """Reproject a raster to a different CRS.

    Parameters
    ----------
    src_raster : str
        Path to input raster.
    dst_raster : str
        Path to output raster.
    dst_crs : rasterio CRS
        Target CRS as a `rasterio.crs.CRS()` object.
    dst_bounds : tuple
        Target raster extent (xmin, ymin, xmax, ymax).
    dst_res : int or float
        Target spatial resolution in `dst_crs` units.
    src_nodata : int or float, optional
        Source nodata value.
    dst_nodata : int or float, optional
        Target nodata value.
    dst_dtype : str, optional
        Target GDAL data type.
    resampling_method : str, optional
        Resampling method: `near`, `bilinear`, `cubic`, `cubicspline`, `lanczos`,
        `average`, `mode`, `max`, `min`, `med`, `q1`, `q3` or `sum`.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    dst_raster : str
        Path to output file.
    """
    logger.info(f"Reprojecting raster `{os.path.basename(src_raster)}`.")
    command = [
        "gdalwarp",
        "-t_srs",
        dst_crs.to_string(),
        "-r",
        resampling_method,
    ]
    command += ["-tr", str(dst_res), str(dst_res)]  # spatial resolution
    command += ["-tap", "-te"] + [str(xy) for xy in dst_bounds]  # align to extent
    if overwrite:
        command += ["-overwrite"]
    command += [src_raster, dst_raster]  # input/output files
    if src_nodata:
        command += ["-srcnodata", str(src_nodata)]
    if dst_nodata:
        command += ["-dstnodata", str(dst_nodata)]
    for creation_opt in GDAL_CO:
        command += ["-co", creation_opt]  # GDAL creation options for GeoTIFF driver
    subprocess.run(command, check=True, env=os.environ, stdout=subprocess.DEVNULL)
    logger.info(f"Reprojected raster {os.path.basename(src_raster)}.")
    return dst_raster


def concatenate_bands(src_files, dst_file, band_descriptions=None):
    """Concatenate multiple rasters into a single multi-band raster.

    Parameters
    ----------
    src_files : list of str
        List of input rasters.
    dst_file : str
        Path to output file.
    band_descriptions : list of str, optional
        Description of each band (GeoTIFF metadata).

    Returns
    -------
    dst_file : str
        Path to output file.
    """
    logger.info(f"Concatenating {len(src_files)} rasters into a single GeoTiff file.")
    with rasterio.open(src_files[0]) as src:
        profile = src.profile
        profile.update(count=len(src_files))
    with rasterio.open(dst_file, "w", **profile) as dst:
        for i, src_file in enumerate(src_files, start=1):
            with rasterio.open(src_file) as src:
                for _, window in dst.block_windows(1):
                    data = src.read(window=window, indexes=1)
                    dst.write(data, window=window, indexes=i)
                if band_descriptions:
                    dst.set_band_description(i, band_descriptions[i - 1])
    logger.info(
        f"Concatenated {len(src_files)} bands into {os.path.basename(dst_file)}."
    )
    return dst_file


def compute_slope(src_dem, dst_file, percent=False, scale=None):
    """Create slope raster from a digital elevation model.

    This command will take a DEM raster and output a 32-bit float raster with
    slope values. You have the option of specifying the type of slope value you
    want: degrees or percent slope. The value -9999 is used as the output nodata
    value.

    Note
    ----
    See `gdaldem documentation <https://gdal.org/programs/gdaldem.html#slope>`_.

    Parameters
    ----------
    src_dem : str
        Path to input DEM.
    dst_file : str
        Path to output raster.
    percent : bool, optional
        Output slope in percents instead of degrees (default=False).
    scale : int, optional
        Ratio of vertical units to horizontal (scale=111120 for WGS84).

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info(f"Computing slope from `{os.path.basename(src_dem)}`.")
    command = ["gdaldem", "slope"]
    if percent:
        command += ["-p"]
    if scale:
        command += ["-s", str(scale)]
    for opt in GDAL_CO:
        command += ["-co", opt]
    command += [src_dem, dst_file]
    logger.info(f"Running command: {' '.join(command)}")
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    logger.info(f"Created slope raster `{os.path.basename(dst_file)}`.")
    return dst_file


def compute_aspect(src_dem, dst_file, trigonometric=False):
    """Create aspect raster from a digital elevation model.

    This command outputs a 32-bit float raster with values between 0° and 360°
    representing the azimuth that slopes are facing. The definition of the
    azimuth is such that : 0° means that the slope is facing the North, 90° it’s
    facing the East, 180° it’s facing the South and 270° it’s facing the West
    (provided that the top of your input raster is north oriented). The aspect
    value -9999 is used as the nodata value to indicate undefined aspect in flat
    areas with slope=0.

    Note
    ----
    See `gdaldem documentation <https://gdal.org/programs/gdaldem.html#aspect>`_.

    Parameters
    ----------
    src_dem : str
        Path to input DEM.
    dst_file : str
        Path to output raster.
    trigonometric : bool, optional
        Return trigonometric angle instead of azimuth (0° East, 90° North, 180°
        West, 270° South).

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info(f"Computing aspect from `{os.path.basename(src_dem)}`.")
    command = ["gdaldem", "aspect"]
    if trigonometric:
        command += ["-trigonometric"]
    for opt in GDAL_CO:
        command += ["-co", opt]
    command += [src_dem, dst_file]
    logger.info(f"Running command: {' '.join(command)}")
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    logger.info(f"Created aspect raster `{os.path.basename(dst_file)}`.")
    return dst_file


def mask_raster(src_raster, geom):
    """Assign nodata value to pixels outside a given geometry.

    The function works for both single-band and multi-band rasters. Source
    raster is overwritten and GDAL compression and tiling options are updated.

    Parameters
    ----------
    src_raster : str
        Path to input raster.
    geom : shapely geometry
        Area of interest (EPSG:4326).
    """
    logger.info(f"Masking `{os.path.basename(src_raster)}` with input geometry.")
    with rasterio.open(src_raster) as src:
        profile = src.profile.copy()

    # Update rasterio profile for better compression and multi-threaded i/o
    compression_opt = default_compression(profile.get("dtype"))
    tiling_opt = default_tiling()
    profile.update(**compression_opt, **tiling_opt)

    geom = transform_geom(
        src_crs=CRS.from_epsg(4326),
        dst_crs=profile.get("crs"),
        geom=geom.__geo_interface__,
    )

    logger.info("Rasterizing input geometry.")
    mask = rasterize(
        shapes=[geom],
        fill=0,
        default_value=1,
        out_shape=(profile.get("height"), profile.get("width")),
        all_touched=True,
        transform=profile.get("transform"),
        dtype="uint8",
    )
    mask = mask != 1

    logger.info("Masking input raster.")
    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        tmpfile = os.path.join(tmpdir, "masked.tif")
        with rasterio.open(src_raster) as src, rasterio.open(
            tmpfile, "w", **profile
        ) as dst:
            for _, window in dst.block_windows():
                mask_w = mask[window.toslices()]
                for bidx in range(1, profile.get("count") + 1):
                    data = src.read(window=window, indexes=bidx)
                    data[mask_w] = profile.get("nodata")
                    dst.write(data, window=window, indexes=bidx)
            for bidx in range(1, profile.get("count") + 1):
                dst.set_band_description(bidx, src.descriptions[bidx - 1])
        try:
            shutil.move(tmpfile, src_raster)
        # shutil.move can fail inside a container when trying to copy xattrs
        # in distributions using SELinux. File is still going to be moved.
        except PermissionError:
            logger.warn(
                f"Permission error when attempting to move `{tmpfile}` to `{src_raster}`."
            )
        logger.info(f"Masked {os.path.basename(src_raster)} raster.")

    return src_raster
