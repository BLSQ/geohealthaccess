"""Preprocessing of input data."""

import logging
import os
import shutil
import subprocess
from math import ceil
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import shape

log = logging.getLogger(__name__)


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
    area = transform_geom(
        src_crs=CRS.from_epsg(4326), dst_crs=dst_crs, geom=geom.__geo_interface__
    )
    left, bottom, right, top = shape(area).bounds
    dst_bounds = (left, bottom, right, top)
    dst_transform = from_origin(left, top, dst_res, dst_res)
    dst_width = ceil(abs(right - left) / dst_res)
    dst_height = ceil(abs(top - bottom) / dst_res)
    return dst_transform, (dst_height, dst_width), dst_bounds


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
    command = ["gdal_merge.py", "-o", dst_file, "-a_nodata", str(nodata)]
    # Add GDAL creation options for GeoTIFF format
    for creation_opt in GDAL_CO:
        command += ["-co", creation_opt]
    command += src_files
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    log.info(f"Merged {len(src_files)} tiles into {os.path.basename(dst_file)}.")
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
    for creation_opt in GDAL_CO:
        command += ["-co", creation_opt]  # GDAL creation options for GeoTIFF driver
    subprocess.run(command, check=True, env=os.environ, stdout=subprocess.DEVNULL)
    log.info(f"Reprojected raster {os.path.basename(src_raster)}.")
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
    with rasterio.open(src_files[0]) as src:
        profile = src.profile
        profile.update(count=len(src_files))
    with rasterio.open(dst_file, "w", **profile) as dst:
        for i, src_file in enumerate(src_files):
            with rasterio.open(src_file) as src:
                dst.write(src.read(1), i + 1)
                if band_descriptions:
                    dst.set_band_description(i + 1, band_descriptions[i])
    log.info(f"Concatenated {len(src_files)} bands into {os.path.basename(dst_file)}.")
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
    command = ["gdaldem", "slope"]
    if percent:
        command += ["-p"]
    if scale:
        command += ["-s", str(scale)]
    for opt in GDAL_CO:
        command += ["-co", opt]
    command += [src_dem, dst_file]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
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
    command = ["gdaldem", "aspect"]
    if trigonometric:
        command += ["-trigonometric"]
    for opt in GDAL_CO:
        command += ["-co", opt]
    command += [src_dem, dst_file]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
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

    mask = rasterize(
        shapes=[geom],
        fill=0,
        default_value=1,
        out_shape=(profile.get("height"), profile.get("width")),
        all_touched=True,
        transform=profile.get("transform"),
        dtype="uint8",
    )

    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        tmpfile = os.path.join(tmpdir, "masked.tif")
        with rasterio.open(src_raster) as src, rasterio.open(
            tmpfile, "w", **profile
        ) as dst:
            for id in range(0, profile["count"]):
                data = src.read(indexes=id + 1)
                data[mask != 1] = profile.get("nodata")
                dst.write_band(id + 1, data)
                dst.set_band_description(id + 1, src.descriptions[id])
        shutil.move(tmpfile, src_raster)
        log.info(f"Masked {os.path.basename(src_raster)} raster.")

    return src_raster
