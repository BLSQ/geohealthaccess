"""Compute per-cell travel times."""


import argparse
import json
import os

import geopandas as gpd
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize

from geohealthaccess import modeling, preprocessing
from geohealthaccess.config import load_config


def base_speed_rasters(input_dir, interm_dir, landcover_speeds,
                       network_speeds, overwrite=False):
    """Compute base speed rasters, i.e. assign per-cell speed from land cover
    and road network information.

    Parameters
    ----------
    input_dir : str
        Path to input data directory (raw data).
    interm_dir : str
        Path to intermediary data directory (preprocessed data).
    landcover_speeds : dict
        Speed associated with each land cover category.
    network_speeds : dict
        Speed and adjustment factors associated with road
        types and properties.
    overwrite : bool, optional
        Overwrite existing base speed rasters if needed.
        Default=False.
    
    Returns
    -------
    landcover_speed : str
        Path to output land cover speed raster.
    roads_speed : str
        Path to output roads speed raster.
    """
    # Assign per-cell speed based on land cover and surface water
    landcover_speed = os.path.join(interm_dir, 'landcover_speed.tif')
    if not os.path.isfile(landcover_speed) or overwrite:
        modeling.speed_from_landcover(
            src_filename=os.path.join(interm_dir, 'landcover.tif'),
            dst_filename=landcover_speed,
            water_filename=os.path.join(interm_dir, 'surface_water.tif'),
            landcover_speeds=landcover_speeds)
    
    # Assign per-cell speed based on roads and paths
    roads_speed = os.path.join(interm_dir, 'roads_speed.tif')
    if not os.path.isfile(roads_speed) or overwrite:
        with rasterio.open(landcover_speed) as src:
            dst_transform = src.transform
            dst_crs = src.crs
            dst_width = src.width
            dst_height = src.height
        osm_dir = os.path.join(input_dir, 'openstreetmap')
        osm_datafile = [f for f in os.listdir(osm_dir)
                        if f.endswith('.gpkg')][0]
        roads_speed = modeling.speed_from_roads(
            src_filename=os.path.join(osm_dir, osm_datafile),
            dst_filename=roads_speed,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_width=dst_width,
            dst_height=dst_height,
            network_speeds=network_speeds)
    
    return landcover_speed, roads_speed


def rasterize_points(points, dst_filename, dst_transform, dst_crs,
                     dst_height, dst_width, overwrite=False):
    """Rasterize a GeoDataFrame of points. TODO: Move function to
    modeling.py or preprocessing.py module.
    """
    if os.path.isfile(dst_filename) and not overwrite:
        return dst_filename
    if not points.crs:
        points.crs = CRS.from_epsg(4326)
    if dst_crs != points.crs:
        points = points.to_crs(dst_crs)

    raster = rasterize(
        shapes=[g.__geo_interface__ for g in points.geometry],
        transform=dst_transform,
        out_shape=(dst_height, dst_width),
        all_touched=True,
        default_value=1,
        fill=0)
    
    profile = rasterio.default_gtiff_profile
    profile.update(
        count=1,
        nodata=255,
        transform=dst_transform,
        crs=dst_crs,
        width=dst_width,
        height=dst_height)

    with rasterio.open(dst_filename, 'w', **profile) as dst:
        dst.write(raster, 1)
    
    return dst_filename


def main():
    # Parse command-line arguments & load configuration
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file',
                        type=str,
                        help='.ini configuration file')
    args = parser.parse_args()
    conf = load_config(args.config_file)
    input_dir = os.path.abspath(conf['DIRECTORIES']['InputDir'])
    interm_dir = os.path.abspath(conf['DIRECTORIES']['IntermDir'])
    output_dir = os.path.abspath(conf['DIRECTORIES']['OutputDir'])

    # Load speed values as dict
    with open(conf['MODELING']['LandCoverSpeeds']) as f:
        landcover_speeds = json.load(f)
    with open(conf['MODELING']['RoadNetworkSpeeds']) as f:
        network_speeds = json.load(f)

    # Base speed rasters
    print('Assigning per-cell travel speed...')
    landcover_speed, roads_speed = base_speed_rasters(
        input_dir, interm_dir, landcover_speeds, network_speeds)

    # Compute friction for each transport mode
    frictions = {}
    for mode in ('car', 'bike', 'walk'):
        print(f'Computing friction surface for transport mode `{mode}`...')
        dst_speed = os.path.join(interm_dir, f'speed_{mode}.tif')
        dst_friction = os.path.join(interm_dir, f'friction_{mode}.tif')
        if not os.path.isfile(dst_friction):
            modeling.combine_speed(landcover_speed, roads_speed, dst_speed,
                                mode=mode)
            modeling.compute_friction(dst_speed, dst_friction, max_time=3600)
        frictions[mode] = dst_friction
    
    # Get target raster profile from friction raster
    with rasterio.open(frictions['car']) as src:
        dst_transform = src.transform
        dst_crs = src.crs
        dst_width = src.width
        dst_height = src.height
    
    # Rasterize destination points
    destinations = {}
    for label, path in conf['DESTINATIONS'].items():
        print(f'Rasterizing destination points `{label}`...')
        points = gpd.read_file(path)
        raster = os.path.join(interm_dir, f'destination_{label}.tif')
        rasterize_points(
            points=points,
            dst_filename=raster,
            dst_crs=dst_crs,
            dst_height=dst_height,
            dst_width= dst_width,
            dst_transform=dst_transform)
        destinations[label] = raster
    
    # Iterate over both transport modes and destination categories
    # and compute travel times for each combination
    for mode in ('car', 'bike', 'walk'):
        for label, path in conf['DESTINATIONS'].items():
            print(f'Computing travel time to `{label}`` using transport mode `{mode}`...')
            
            os.makedirs(output_dir, exist_ok=True)
            dst_cost = os.path.join(
                output_dir, f'cost_{mode}_{label}.tif')
            dst_nearest = os.path.join(
                output_dir, f'nearest_{mode}_{label}.tif')
            dst_backlink = os.path.join(
                output_dir, f'backlink_{mode}_{label}.tif')
            
            if mode in ('car', 'bike'):
                modeling.isotropic_costdistance(
                    src_friction=frictions[mode],
                    src_target=destinations[label],
                    dst_cost=dst_cost,
                    dst_nearest=dst_nearest,
                    dst_backlink=dst_backlink,
                    extent=None,
                    max_memory=8000)
            
            if mode == 'walk':
                modeling.anisotropic_costdistance(
                    src_friction=frictions[mode],
                    src_target=destinations[label],
                    src_elevation=os.path.join(interm_dir, 'elevation.tif'),
                    dst_cost=dst_cost,
                    dst_nearest=dst_nearest,
                    dst_backlink=dst_backlink,
                    extent=None,
                    max_memory=8000)

    # Post-processing of output rasters
    print('Post-processing output rasters...')
    country_code = conf['AREA']['CountryCode']
    rasters = [os.path.join(output_dir, f) for f in os.listdir(output_dir)
               if f.endswith('.tif')]
    for raster in rasters:
        if os.path.basename(raster).startswith('cost'):
            preprocessing.mask_raster(raster, country_code, -1)
            modeling.seconds_to_minutes(raster)

    print('Done.')
    return


if __name__ == '__main__':
    main()
