"""Preprocessing of input data."""

import os
from math import ceil

import rasterio
from rasterio import Affine
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
