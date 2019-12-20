"""Preprocess input data."""

import argparse
import os
import shutil

from geohealthaccess import preprocessing, utils
from geohealthaccess.config import load_config


def preprocess_land_cover(input_dir, output_dir, primary_raster):
    """Merge and reproject land cover tiles.
    
    Parameters
    ----------
    input_dir : str
        Directory that contains raw land cover tiles.
    output_dir : str
        Output directory for preprocessed files.
    primary_raster : str
        Path to primary raster (main grid and extent).
    """
    LAND_COVERS = ['bare', 'crops', 'grass', 'moss', 'shrub', 'snow', 'tree',
                   'urban', 'water-permanent', 'water-seasonal']
    for land_cover in LAND_COVERS:
        aligned_raster = os.path.join(output_dir,
                                      f'landcover_{land_cover}.tif')
        # Avoid if preprocessed raster already exists
        if os.path.isfile(aligned_raster):
            continue
        # Merge all raster tiles into a single GeoTIFF
        layer_name = f'{land_cover}-coverfraction-layer'
        filenames = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                     if layer_name in f and f.endswith('.tif')]
        merged_raster = os.path.join(output_dir,
                                     f'landcover_{land_cover}_merged.tif')
        preprocessing.merge_raster_tiles(filenames, merged_raster)
        # Align grid with primary raster
        preprocessing.align_raster(merged_raster, aligned_raster, primary_raster,
                                   resample_algorithm=1)
        os.remove(merged_raster)
    return output_dir


def preprocess_elevation(input_dir, output_dir, primary_raster):
    """Merge and reproject SRTM elevation tiles.
    
    Parameters
    ----------
    input_dir : str
        Directory that contains raw land cover tiles.
    output_dir : str
        Output directory for preprocessed files.
    primary_raster : str
        Path to primary raster (main grid and extent).
    """
    aligned_raster = os.path.join(output_dir, 'elevation.tif')
    if os.path.isfile(aligned_raster):
        return
    filenames = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                 if f.endswith('.hgt')]
    merged_raster = os.path.join(output_dir, 'elevation_merged.tif')
    preprocessing.merge_raster_tiles(filenames, merged_raster)
    preprocessing.align_raster(merged_raster, aligned_raster, primary_raster,
                               resample_algorithm=1)
    os.remove(merged_raster)
    return


def preprocess_surface_water(input_dir, output_dir, primary_raster):
    """Merge and reproject GSW tiles.
    
    Parameters
    ----------
    input_dir : str
        Directory that contains raw land cover tiles.
    output_dir : str
        Output directory for preprocessed files.
    primary_raster : str
        Path to primary raster (main grid and extent).
    """
    aligned_raster = os.path.join(output_dir, 'surface-water.tif')
    if os.path.isfile(aligned_raster):
        return
    filenames = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                 if f.endswith('.tif')]
    merged_raster = os.path.join(output_dir, 'surface-water_merged.tif')
    preprocessing.merge_raster_tiles(filenames, merged_raster)
    preprocessing.align_raster(merged_raster, aligned_raster, primary_raster,
                               resample_algorithm=6)
    preprocessing.set_nodata(aligned_raster, 255)
    os.remove(merged_raster)
    return


def preprocess_population(input_dir, output_dir, primary_raster):
    """Preprocess Worldpop data.
    
    Parameters
    ----------
    input_dir : str
        Directory that contains raw land cover tiles.
    output_dir : str
        Output directory for preprocessed files.
    primary_raster : str
        Path to primary raster (main grid and extent).
    """    
    filename = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                if f.endswith('.tif') and 'ppp' in f][0]
    aligned_raster = os.path.join(output_dir, 'population.tif')
    if os.path.isfile(aligned_raster):
        return
    
    # If population raster is the primary raster, just copy the original file
    if os.path.abspath(filename) == os.path.abspath(primary_raster): 
        shutil.copyfile(filename, os.path.join(output_dir, 'population.tif'))
    else:
        preprocess_population.align_raster(filename, aligned_raster, primary_raster,
                                           resample_algorithm=1)
    return


def preprocess(input_dir, output_dir, primary_raster, country):
    """Preprocess input data. Merge tiles, reproject to common grid,
    mask invalid areas, and ensure correct raster compression.
    
    Parameters
    ----------
    input_dir : str
        Main input directory which contains raw data.
    output_dir : str
        Output directory for preprocessed files.
    primary_raster : str
        Path to primary raster (main grid and extent).
    country : str
        3-letters country code.
    """
    os.makedirs(output_dir, exist_ok=True)
    print('Preprocessing land cover data...')
    preprocess_land_cover(os.path.join(input_dir, 'land_cover'),
                          output_dir,
                          primary_raster)
    print('Preprocessing elevation data...')
    preprocess_elevation(os.path.join(input_dir, 'elevation'),
                         output_dir,
                         primary_raster)
    print('Preprocessing surface water data...')
    preprocess_surface_water(os.path.join(input_dir, 'water'),
                             output_dir,
                             primary_raster)
    print('Preprocessing population data...')
    preprocess_population(os.path.join(input_dir, 'population'),
                          output_dir,
                          primary_raster)
    print('Masking data outside country boundaries...')
    for filename in os.listdir(output_dir):
        if filename.endswith('.tif'):
            preprocessing.mask_raster(os.path.join(output_dir, filename),
                                      country)
    print('Compress rasters...')
    for filename in os.listdir(output_dir):
        if filename.endswith('.tif'):
            preprocessing.compress_raster(os.path.join(output_dir, filename))
    print('Done!')


def main():
    # Parse command-line arguments & load configuration
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file',
                        type=str,
                        help='.ini configuration file')
    args = parser.parse_args()
    conf = load_config(args.config_file)
    
    # Get path to primary raster from config file
    input_dir = conf['DIRECTORIES']['InputDir']
    label = conf['AREA']['PrimaryRaster']
    filename = os.listdir(os.path.join(input_dir, label))[0]
    primary_raster = os.path.join(input_dir, label, filename)

    # Run script
    preprocess(input_dir=input_dir,
               output_dir=conf['DIRECTORIES']['IntermDir'],
               primary_raster=primary_raster,
               country=conf['AREA']['CountryCode'])


if __name__ == '__main__':
    main()
