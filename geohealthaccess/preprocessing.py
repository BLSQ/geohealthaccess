"""Preprocessing of input data."""

import os
from math import ceil
from pkg_resources import resource_string, resource_filename
import json
import shutil
import subprocess

from osgeo import gdal
import rasterio
from rasterio import Affine
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from shapely.geometry import shape
import geopandas as gpd
from tqdm import tqdm

from geohealthaccess import utils


def gdal_dtype(dtype):
    """Convert dtype string to GDAL GDT object."""
    GDAL_DTYPES = {
        'uint8': gdal.GDT_Byte,
        'uint16': gdal.GDT_UInt16,
        'int16': gdal.GDT_Int16,
        'uint32': gdal.GDT_UInt32,
        'int32': gdal.GDT_Int32,
        'float32': gdal.GDT_Float32,
        'float64': gdal.GDT_Float64,
    }
    if dtype.lower() not in GDAL_DTYPES:
        raise ValueError('Unrecognized data type.')
    return GDAL_DTYPES[dtype.lower()]


def create_grid(geom, dst_crs, dst_res):
    """Create a raster grid for a given area of interest.

    Parameters
    ----------
    geom: shapely geometry
        Area of interest.
    dst_crs : dict-like CRS object
        Target CRS.
    dst_res : int or float
        Spatial resolution (in dst_srs units).
    
    Returns
    -------
    transform: Affine
        Output affine transform object.
    width: int
        Output width.
    height: int
        Output height.
    bounds : tuple
        AOI bounds.
    """
    area = transform_geom(
        src_crs=CRS.from_epsg(4326),
        dst_crs=dst_crs,
        geom=geom.__geo_interface__)
    left, bottom, right, top = shape(area).bounds
    dst_bounds = (left, bottom, right, top)
    dst_transform = from_origin(left, top, dst_res, dst_res)
    dst_width = ceil(abs(right - left) / dst_res)
    dst_height = ceil(abs(top - bottom) / dst_res)
    return dst_transform, dst_width, dst_height, dst_bounds


def merge_tiles(filenames, dst_filename, nodata=-1):
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


def reproject_raster(src_raster, dst_filename, dst_crs, resample_algorithm,
                     dst_bounds=None, dst_shape=None, dst_res=None,
                     dst_nodata=None, dst_dtype=None):
    """Reproject a source raster to a target CRS identified by its EPSG code.

    Parameters
    ----------
    src_raster : str
        Path to source raster.
    dst_filename : str
        Path to output raster.
    dst_crs : CRS object
        Target spatial reference system.
    resample_algorithm : int
        GDAL code of the resampling algorithm, e.g. 0=NearestNeighbour,
        1=Bilinear, 2=Cubic, 5=Average, 6=Mode...
    dst_bounds : tuple, optional
        Output bounds (xmin, ymin, xmax, ymax) in target SRS.
    dst_shape : tuple, optional
        Output raster shape (width, height).
    dst_res : float, optional
        Output spatial resolution in target SRS units.
    dst_nodata : float or int, optional
        Output nodata value.
    dst_dtype : str
        Target data type (Int16, UInt16, UInt32, Float32, etc.).

    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    src_dataset = gdal.Open(src_raster)
    creation_options = ['TILED=YES', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256',
                        'COMPRESS=LZW', 'PREDICTOR=2', 'NUM_THREADS=ALL_CPUS']
    options = {'format': 'GTiff',
               'dstSRS': dst_crs.to_string(),
               'resampleAlg': resample_algorithm,
               'creationOptions': creation_options}
    if dst_bounds:
        options.update(outputBounds=dst_bounds)
    if dst_shape:
        options.update(width=dst_shape[0], height=dst_shape[1])
    if dst_res:
        options.update(xRes=dst_res, yRes=dst_res)
    if dst_nodata:
        options.update(dstNodata=dst_nodata)
    if dst_dtype:
        options.update(outputType=gdal_dtype(dst_dtype))
    warp_options = gdal.WarpOptions(**options)
    dst_dataset = gdal.Warp(dst_filename, src_dataset, options=warp_options)
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

    with rasterio.open(src_raster) as src:
        src_profile = src.profile
        src_nodata = src.nodata
        src_width, src_height = src.width, src.height
        src_transform, src_crs = src.transform, src.crs

    geom = utils.country_geometry(country)
    geom = transform_geom(
        src_crs=CRS.from_epsg(4326),
        dst_crs=src_crs,
        geom=geom.__geo_interface__)

    country_mask = rasterize(
        shapes=[geom],
        fill=0,
        default_value=1,
        out_shape=(src_height, src_width),
        all_touched=True,
        transform=src_transform,
        dtype=rasterio.uint8)
    
    # Store band descriptions
    with rasterio.open(src_raster) as src:
        descriptions = src.descriptions
    
    dst_dir = os.path.dirname(src_raster)
    dst_filename = os.path.join(dst_dir, 'masked.tif')
    
    with rasterio.open(src_raster) as src, \
         rasterio.open(dst_filename, 'w', **src_profile) as dst:
        for id in range(0, src_profile['count']):
            data = src.read(indexes=id+1)
            data[country_mask != 1] = src_nodata
            dst.write_band(id+1, data)
            dst.set_band_description(id+1, descriptions[id])
    
    shutil.move(dst_filename, src_raster)

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
