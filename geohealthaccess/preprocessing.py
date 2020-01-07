"""Preprocessing of input data."""

import os
from math import ceil
from pkg_resources import resource_string, resource_filename
import json

from osgeo import gdal
import rasterio
from rasterio import Affine
from rasterio.features import rasterize
import geopandas as gpd
from tqdm import tqdm

from geohealthaccess import utils


def merge_raster_tiles(filenames, output_file):
    """Merge multiple rasters with same CRS and spatial resolution into
    a single GTiff file. Partially adapted from
    https://github.com/mapbox/rasterio/blob/master/rasterio/merge.py to
    not load all input datasets into memory before writing to disk.
    """
    # Get metadata from first file
    with rasterio.open(filenames[0]) as src:
        nodata = src.nodata
        dtype = src.dtypes[0]
        crs = src.crs
        res = src.transform.a
    
    # Find the extent of the output mosaic
    xs, ys = [], []
    for filename in filenames:
        with rasterio.open(filename) as src:
            w, s, e, n = src.bounds
            xs.extend([w, e])
            ys.extend([s, n])
    dst_w, dst_s, dst_e, dst_n = min(xs), min(ys), max(xs), max(ys)
    
    # Scale affine transformation to spatial resolution
    dst_transform = Affine.translation(dst_w, dst_n)
    dst_transform *= Affine.scale(res, -res)
    
    # Compute shape of the output mosaic and adjust bounds
    dst_width = int(ceil((dst_e - dst_w) / res))
    dst_height = int(ceil((dst_n - dst_s) / res))
    dst_e, dst_s = dst_transform * (dst_width, dst_height)
    
    dst_profile = rasterio.profiles.DefaultGTiffProfile()
    dst_profile.update(transform=dst_transform, width=dst_width,
                       height=dst_height, dtype=dtype,
                       crs=crs, nodata=nodata, count=1)
    
    progress = tqdm(total=len(filenames))
    dst = rasterio.open(output_file, 'w', **dst_profile)
    for filename in filenames:
        src = rasterio.open(filename)
        # Destination window
        src_w, src_s, src_e, src_n = src.bounds
        dst_window = rasterio.windows.from_bounds(
            src_w, src_s, src_e, src_n, dst_transform)
        # Write data
        dst.write(src.read(1), window=dst_window, indexes=1)
        src.close()
        progress.update(1)
    dst.close()
    progress.close()

    return output_file


def align_raster(src_raster, dst_filename, primary_raster, resample_algorithm):
    """Align a source raster to be in the same grid as a given
    primary raster.
    
    Parameters
    ----------
    src_raster : str
        Path to source raster that will be reprojected.
    dst_filename : str
        Path to output raster.
    primary_raster : str
        Path to primary raster. Source raster will be reprojected
        to the same grid.
    resample_algorithm : int
        GDAL code of the resampling algorithm, e.g. 0=NearestNeighbour,
        1=Bilinear, 2=Cubic, 5=Average, 6=Mode...
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    # Get information on target grid
    with rasterio.open(primary_raster) as src:
        dst_bounds = src.bounds
        dst_crs = src.crs
        dst_width, dst_height = src.width, src.height
    
    # Reproject source raster
    src_dataset = gdal.Open(src_raster)
    options = gdal.WarpOptions(
        format='GTiff',
        outputBounds=dst_bounds,
        width=dst_width,
        height=dst_height,
        resampleAlg=resample_algorithm)
    dst_dataset = gdal.Warp(dst_filename, src_dataset, options=options)
    return dst_filename


def set_nodata(src_raster, nodata, overwrite=False):
    """Set nodata value for a given raster."""
    with rasterio.open(src_raster) as src:
        if src.nodata and not overwrite:
            return
        else:
            dst_profile = src.profile.copy()
            dst_profile.update(nodata=nodata)
            with rasterio.open(src_raster, 'w', **dst_profile) as dst:
                dst.write(src.read(1), 1)
    return


def compress_raster(src_raster):
    """Ensure that src_raster uses LZW compression."""
    with rasterio.open(src_raster) as src:
        if src.profile.get('compress') == 'lzw':
            return
        else:
            dst_profile = src.profile.copy()
            dst_profile['compress'] = 'lzw'
            with rasterio.open(src_raster, 'w', **dst_profile) as dst:
                dst.write(src.read(1), 1)
    return


def mask_raster(src_raster, country):
    """Assign nodata value to pixels outside a country boundaries."""
    geom = utils.country_geometry(country)
    with rasterio.open(src_raster) as src:
        src_profile = src.profile
        src_nodata = src.nodata
        src_width, src_height = src.width, src.height
        src_transform, src_crs = src.transform, src.crs
        data = src.read(1)
    country_mask = rasterize(
        shapes=[geom.__geo_interface__],
        fill=0,
        default_value=1,
        out_shape=(src_height, src_width),
        all_touched=True,
        transform=src_transform,
        dtype=rasterio.uint8)
    data[country_mask != 1] = src_nodata
    with rasterio.open(src_raster, 'w', **src_profile) as dst:
        dst.write(data, 1)
    return


def set_blocksize(raster, size=256):
    """Set tile blocksize of a given raster in pixels."""
    with rasterio.open(raster) as src:
        profile = src.profile
        # Avoid if blocksize is already correct
        if profile.get('blockxsize') == size:
            return
        data = src.read(1)
    profile.update(
        tiled=True,
        blockxsize=size,
        blockysize=size)
    # Rewrite raster to disk
    with rasterio.open(raster, 'w', **profile) as dst:
        dst.write(data, 1)
    return
