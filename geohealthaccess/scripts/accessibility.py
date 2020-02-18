"""Compute per-cell travel times."""


import argparse
import json
import os

import geopandas as gpd
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
import whitebox

from geohealthaccess import modeling
from geohealthaccess.config import load_config


def base_speed_rasters(input_dir, interm_dir, landcover_speeds,
                       network_speeds):
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
    
    Returns
    -------
    landcover_speed : str
        Path to output land cover speed raster.
    roads_speed : str
        Path to output roads speed raster.
    """
    # Assign per-cell speed based on land cover and surface water
    print('Assigning speed values based on land cover...')
    landcover_speed = modeling.speed_from_landcover(
        src_filename=os.path.join(interm_dir, 'landcover.tif'),
        dst_filename=os.path.join(interm_dir, 'landcover_speed.tif'),
        water_filename=os.path.join(interm_dir, 'surface_water.tif'),
        landcover_speeds=landcover_speeds)
    
    # Assign per-cell speed based on roads and paths
    print('Assigning speed values based on the road network...')
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
        dst_filename=os.path.join(interm_dir, 'roads_speed.tif'),
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_width=dst_width,
        dst_height=dst_height,
        network_speeds=network_speeds)
    
    return landcover_speed, roads_speed




def _compute_friction(input_dir, interm_dir, landcover_speeds, network_speeds):
    """Assign per-cell speed from land cover and road network. Then compute
    friction raster from speed.

    DEPERECATED.

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
    
    Returns
    -------
    speed_rasters : list
        List of paths to output speed rasters (one per transport mode).
    """
    # Assign per-cell speed based on land cover and surface water
    print('Assigning speed values based on land cover...')
    landcover_speed = modeling.speed_from_landcover(
        src_filename=os.path.join(interm_dir, 'landcover.tif'),
        dst_filename=os.path.join(interm_dir, 'landcover_speed.tif'),
        water_filename=os.path.join(interm_dir, 'surface_water.tif'),
        landcover_speeds=landcover_speeds)
    
    # Assign per-cell speed based on roads and paths
    print('Assigning speed values based on the road network...')
    with rasterio.open(landcover_speed) as src:
        dst_transform = src.transform
        dst_crs = src.crs
        dst_width = src.width
        dst_height = src.height
    osm_dir = os.path.join(input_dir, 'openstreetmap')
    osm_datafile = [f for f in os.listdir(osm_dir)
                    if f.endswith('.gpkg')][0]
    road_speed = modeling.speed_from_roads(
        src_filename=os.path.join(osm_dir, osm_datafile),
        dst_filename=os.path.join(interm_dir, 'road_speed.tif'),
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        dst_width=dst_width,
        dst_height=dst_height,
        network_speeds=network_speeds)
    
    # Compute speed rasters for bicycling, walking, and car
    speed_rasters = []
    for mode in ('car', 'bike', 'walk'):
        speed = os.path.join(interm_dir, f'speed_{mode}.tif')
        modeling.combined_speed(landcover_speed, road_speed, speed, mode=mode)
        speed_rasters.append(speed)

    return speed_rasters


def rasterize_points(points, dst_filename, dst_transform, dst_crs,
                     dst_height, dst_width):
    """Rasterize a GeoDataFrame of points. TODO: Move function to
    modeling.py or preprocessing.py module.
    """
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


def _compute_traveltime(destinations, friction, dst_dir, label):
    """DEPRECATED."""
    os.makedirs(dst_dir, exist_ok=True)
    out_accum = os.path.join(dst_dir, f'accumulated_cost_{label}.tif')
    out_backlink = os.path.join(dst_dir, f'backlink_{label}.tif')
    wbt = whitebox.WhiteboxTools()
    wbt.cost_distance(
        source=destinations,
        cost=friction,
        out_accum=out_accum,
        out_backlink=out_backlink)
    return out_accum


def compute_traveltime(destinations, speed, elevation, dst_dir,
                       label, max_memory=8000):
    """Compute accessibility map using r.walk.accessmod GRASS module.

    Parameters
    ----------
    destinations : str
        Path to the raster that contains destination points (non-null
        values).
    speed : str
        Path to input speed raster (in km/h).
    elevation : str
        Path to input elevation raster (in meters).
    dst_dir : str
        Path to output directory.
    label : str
        Label of the analysis.
    max_memory : int, optional
        Max. memory (in MB) used by the GRASS module.

    Returns
    -------
    dst_cost : str
        Path to output accumulated cost raster (the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster.
    dst_backlink : str
        Path to output movement directions raster.
    """
    os.makedirs(dst_dir, exist_ok=True)
    dst_cost = os.path.join(dst_dir, f'accumulated_cost_{label}.tif')
    dst_nearest = os.path.join(dst_dir, f'nearest_{label}.tif')
    dst_backlink = os.path.join(dst_dir, f'backlink_{label}.tif')
    modeling.compute_traveltime(
        src_speed=speed,
        src_elevation=elevation,
        src_target=destinations,
        dst_cost=dst_cost,
        dst_nearest=dst_nearest,
        dst_backlink=dst_backlink,
        max_memory=max_memory)
    return dst_cost, dst_nearest, dst_backlink


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
    landcover_speed, roads_speed = base_speed_rasters(
        input_dir, interm_dir, landcover_speeds, network_speeds)

    # Take into account transport mode
    speed_rasters = {}
    for mode in ('car', 'bike', 'walk'):
        fname = os.path.join(interm_dir, f'speed_{mode}.tif')
        modeling.combined_speed(landcover_speed, roads_speed, fname, mode)
        speed_rasters[mode] = fname
    
    # Get target raster profile from speed raster
    with rasterio.open(speed_rasters['car']) as src:
        dst_transform = src.transform
        dst_crs = src.crs
        dst_width = src.width
        dst_height = src.height
    
    # Iterate over both transport modes and destination categories
    for mode in ('car', 'bike', 'walk'):
        for label, path in conf['DESTINATIONS'].items():

            print(f'Computing travel time to {label} using transport mode `{mode}`...')
            
            # Rasterize destination points
            points = gpd.read_file(path)
            points_raster = os.path.join(
                interm_dir, f'points_{mode}_{label}.tif')
            rasterize_points(
                points=points,
                dst_filename=points_raster,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_height=dst_height,
                dst_width=dst_width
            )

            # Compute travel time
            compute_traveltime(
                destinations=points_raster,
                speed=speed_rasters[mode],
                elevation=os.path.join(interm_dir, 'elevation.tif'),
                dst_dir=output_dir,
                label=f'{mode}_{label}',
                max_memory=8000
            )

    print('Done.')
    return


if __name__ == '__main__':
    main()
