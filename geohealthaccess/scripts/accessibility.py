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


def compute_friction(input_dir, interm_dir, landcover_speeds, network_speeds):
    """Assign per-cell speed from land cover and road network. Then compute
    friction raster from speed.

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
    friction : str
        Path to output raster.
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
    
    # Combine both speed rasters by keeping max. speed value
    print('Combining speed rasters...')
    speed = os.path.join(interm_dir, 'speed.tif')
    modeling.combine_speed_rasters(landcover_speed, road_speed, speed) 

    # Friction raster, i.e. time to cross each pixel
    print('Computing friction raster...')
    friction = os.path.join(interm_dir, 'friction.tif')
    modeling.compute_friction(speed, friction, max_time=3600)

    return friction


def rasterize_points(points, dst_filename, dst_transform, dst_crs,
                     dst_height, dst_width):
    """Rasterize a GeoDataFrame of points."""
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


def compute_traveltime(destinations, friction, dst_dir, label):
    """TODO."""
    out_accum = os.path.join(dst_dir, f'accumulated_cost_{label}.tif')
    out_backlink = os.path.join(dst_dir, f'backlink_{label}.tif')
    wbt = whitebox.WhiteboxTools()
    wbt.cost_distance(
        source=destinations,
        cost=friction,
        out_accum=out_accum,
        out_backlink=out_backlink)
    return out_accum


def main():
    # Parse command-line arguments & load configuration
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file',
                        type=str,
                        help='.ini configuration file')
    args = parser.parse_args()
    conf = load_config(args.config_file)
    interm_dir = conf['DIRECTORIES']['IntermDir']

    # Load speed values as dict
    with open(conf['MODELING']['LandCoverSpeeds']) as f:
        landcover_speeds = json.load(f)
    with open(conf['MODELING']['RoadNetworkSpeeds']) as f:
        network_speeds = json.load(f)

    # Run script
    friction = compute_friction(
        input_dir=conf['DIRECTORIES']['InputDir'],
        interm_dir=interm_dir,
        landcover_speeds=landcover_speeds,
        network_speeds=network_speeds)

    with rasterio.open(friction) as src:
        dst_transform, dst_crs = src.transform, src.crs
        dst_width, dst_height = src.width, src.height

    for label, path in conf['DESTINATIONS'].items():

        points = gpd.read_file(path)
        points_raster = os.path.join(interm_dir, f'points_{label}.tif')

        print(f'Computing travel time to {label}...')

        rasterize_points(
            points=points,
            dst_filename=points_raster,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_height=dst_height,
            dst_width=dst_width)

        compute_traveltime(
            destinations=points_raster,
            friction=friction,
            dst_dir=conf['DIRECTORIES']['OutputDir'],
            label=label)
    
    print('Done.')

    return


if __name__ == '__main__':
    main()
