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
    dst_dataset = gdal.Warp(dst_filename, src_dataset, optiresource_filenons=options)
    return dst_filename


def get_network_speed(highway, tracktype=None, smoothness=None, surface=None,
                      alt_network_speeds=None):
    """Get the speed in km/h associated with a given network segment, based
    on the `road-network.json` resource file.

    Parameters
    ----------
    highway : str
        OSM highway tag.
    tracktype : str, optional
        OSM tracktype tag.
    smoothness : str, optional
        OSM smoothness tag.
    surface : str, optional
        OSM surface tag.
    alt_network_speeds : str, optional
        Path to an alternative JSON file for network speeds.

    Returns
    -------
    speed : int
        Speed in km/h.
    """
    # Use alternative JSON file if provided
    if alt_network_speeds:
        with open(alt_network_speeds) as f:
            network_speeds = json.load(f)
    else:
        with open(resource_filename(__name__, 'resources/road-network.json')) as f:
            network_speeds = json.load(f)

    if highway not in network_speeds['highway']:
        return None
    
    base_speed = network_speeds['highway'][highway]
    
    # Adjust base speed based on other OSM tags
    tracktype = network_speeds['tracktype'].get(tracktype, 1)
    smoothness = network_speeds['smoothness'].get(smoothness, 1)
    surface = network_speeds['surface'].get(surface, 1)
    speed = base_speed * min(tracktype, smoothness, surface)
    
    return speed


def rasterize_network(src_data, dst_filename, primary_raster):
    """Convert network geometries to a raster with cell values equal
    to speed in km/h.

    Parameters
    ----------
    src_data : str
        Path to input network geometries (with the following columns: geometry,
        highway, smoothness, tracktype and surface).
    dst_filename : str
        Path to output raster.
    primary_raster : str
        Path to a primary raster to identify target resolution, CRS and extent.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    with rasterio.open(primary_raster) as src:
        dst_width, dst_height = src.width, src.height
        dst_crs = src.crs
        dst_transform = src.transform

    network = gpd.read_file(src_data)
    network = network[network.geom_type == 'LineString']

    shapes = []
    for _, row in network.iterrows():
        speed = get_network_speed(
            row.highway, row.tracktype, row.smoothness, row.surface)
        if speed:
            shapes.append((row.geometry, int(speed)))
    
    speed_raster = rasterize(
        shapes=shapes,
        out_shape=(dst_height, dst_width),
        transform=dst_transform,
        fill=0,
        all_touched=True,
        dtype=rasterio.dtypes.uint8)
    
    dst_profile = rasterio.profiles.DefaultGTiffProfile()
    dst_profile.update(
        count=1,
        crs=dst_crs,
        width=dst_width,
        height=dst_height,
        transform=dst_transform,
        dtype=rasterio.dtypes.uint8,
        nodata=255)
    
    with rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        dst.write(speed_raster, 1)
    return dst_filename