"""Preprocessing of input data."""

import os
from math import ceil
from pkg_resources import resource_string, resource_filename
import json
import subprocess

from osgeo import gdal
import rasterio
from rasterio import Affine
from rasterio.features import rasterize
import geopandas as gpd
from tqdm import tqdm

from geohealthaccess import utils


def merge_raster_tiles(filenames, dst_filename, nodata=-1):
    """Merge multiple rasters with same CRS and spatial resolution into
    a single GTiff file. Use gdal_merge.py CLI utility.
    
    Parameters
    ----------
    filenames : list
        Paths to raster tiles.
    dst_filename : str
        Path to output raster.
    nodata : float, optional
        Nodata value of the output raster.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    args = ['-o', dst_filename]
    args += ['-a_nodata', str(nodata)]
    args += filenames
    subprocess.run(['gdal_merge.py'] + args)
    return dst_filename


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


def list_landcover_layers(src_dir):
    """List land cover layers available in a given
    directory. Return a list of tuples (name, file_path).
    """
    layers = []
    for fname in os.listdir(src_dir):
        if 'landcover' in fname and fname.endswith('.tif'):
            # Avoid if 'speed' is found in the filename
            # It's not a land cover layer
            if 'speed' in fname:
                continue
            basename = fname.replace('.tif', '')
            layername = basename.split('_')[1]
            layerpath = os.path.join(src_dir, fname)
            layers.append((layername, layerpath))
    return layers


def create_landcover_stack(src_dir, dst_filename):
    """Create a multi-band GeoTIFF stack of land cover
    layers.
    """
    layers = list_landcover_layers(src_dir)
    with rasterio.open(layers[0][1]) as src:
        dst_profile = src.profile
        dst_profile.update(
            count=len(layers),
            tiled=True,
            blockxsize=256,
            blockysize=256)

    with rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        for id, layer in enumerate(layers, start=1):
            with rasterio.open(layer[1]) as src:
                dst.write_band(id, src.read(1))
                dst.set_band_description(id, layer[0])

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
                dst.write(src.read())
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
                dst.write(src.read())
    return


def mask_raster(src_raster, country):
    """Assign nodata value to pixels outside a country boundaries."""
    geom = utils.country_geometry(country)
    with rasterio.open(src_raster) as src:
        src_profile = src.profile
        src_nodata = src.nodata
        src_width, src_height = src.width, src.height
        src_transform, src_crs = src.transform, src.crs

    country_mask = rasterize(
        shapes=[geom.__geo_interface__],
        fill=0,
        default_value=1,
        out_shape=(src_height, src_width),
        all_touched=True,
        transform=src_transform,
        dtype=rasterio.uint8)

    for id in range(0, src_profile['count']):
        with rasterio.open(src_raster) as src:
            data = src.read(id+1)
            data[country_mask != 1] = src_nodata
        with rasterio.open(src_raster, 'w', **src_profile) as dst:
            dst.write(data, id+1)

    return src_raster


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
