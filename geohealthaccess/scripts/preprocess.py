"""Preprocess input data."""

import os
import shutil

import click
from tqdm.auto import tqdm
from geohealthaccess import utils, preprocessing


@click.command()
@click.option(
    '--input-dir', '-d', type=click.Path(), help='Input data directory.')
@click.option(
    '--output-dir', '-o', type=click.Path(), help='Output data directory.')
@click.option(
    '--primary-raster', '-p', type=click.Path(), help='Primary raster.')
@click.option(
    '--country', '-c', type=str, help='Country three-letters code.'
)
def preprocess(input_dir, output_dir, primary_raster, country):
    """Preprocess input data."""
    os.makedirs(output_dir, exist_ok=True)
    click.echo('Preprocessing land cover data...')
    preprocess_land_cover(
        os.path.join(input_dir, 'land_cover'),
        output_dir,
        primary_raster
    )

    click.echo('Preprocessing topographic data...')
    preprocess_topography(
        os.path.join(input_dir, 'topography'),
        output_dir,
        primary_raster
    )

    click.echo('Preprocessing surface water data...')
    preprocess_surface_water(
        os.path.join(input_dir, 'water'),
        output_dir,
        primary_raster
    )

    click.echo('Preprocessing population data...')
    preprocess_population(
        os.path.join(input_dir, 'population'),
        output_dir,
        primary_raster
    )

    click.echo('Masking data outside country boundaries...')
    for fname in os.listdir(output_dir):
        if fname.endswith('.tif'):
            preprocessing.mask_raster(
                os.path.join(output_dir, fname),
                country)

    click.echo('Compress raster data...')
    for fname in os.listdir(output_dir):
        if fname.endswith('.tif'):
            preprocessing.compress_raster(os.path.join(output_dir, fname))
    
    click.echo('Done.')
    return


def preprocess_land_cover(input_dir, output_dir, primary_raster):
    """Preprocess land cover raster data."""
    LAND_COVERS = [
        'bare',
        'crops',
        'grass',
        'moss',
        'shrub',
        'snow',
        'tree',
        'urban',
        'water-permanent',
        'water-seasonal'
    ]
    
    for land_cover in LAND_COVERS:

        aligned_raster = os.path.join(output_dir, f'landcover_{land_cover}.tif')
        if os.path.isfile(aligned_raster):
            continue
        
        # Merge all raster tiles into a single GeoTIFF
        layer_name = f'{land_cover}-coverfraction-layer'
        filenames = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                     if layer_name in f and f.endswith('.tif')]
        merged_raster = os.path.join(output_dir, f'landcover_{land_cover}_merged.tif')
        preprocessing.merge_raster_tiles(filenames, merged_raster)

        # Align grid with primary raster
        preprocessing.align_raster(merged_raster, aligned_raster, primary_raster,
                                   resample_algorithm=1)
        os.remove(merged_raster)

    return output_dir


def preprocess_topography(input_dir, output_dir, primary_raster):
    """Preprocess topographic raster data."""
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
    """Preprocess surface water raster data."""
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
    """Preprocess population data."""
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
