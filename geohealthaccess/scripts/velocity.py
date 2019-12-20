"""Assign per-cell travel speeds depending on
transport network and land cover.
"""

import argparse
import json
import os

import rasterio

from geohealthaccess import modeling
from geohealthaccess.config import load_config


def assign_speeds(osm_dir, landcover_dir, network_speeds,
                  landcover_speeds, output_dir):
    """Assign per-cell travel speeds based on transport network
    and land cover.
    
    Parameters
    ----------
    osm_dir : str
        Directory that contains OSM road data.
    landcover_dir : str
        Directory that contains land cover data.
    network_speeds : dict
        Speed values and factors associated with each
        OSM road type.
    landcover_speeds : dict
        Speed values associated with each land cover.
    output_dir : str
        Output directory.
    """
    # Get raster CRS, transform and dimensions from
    # any preprocessed GeoTIFF
    primary_raster = [f for f in os.listdir(landcover_dir)
                      if f.endswith('.tif')][0]
    with rasterio.open(os.path.join(landcover_dir, primary_raster)) as src:
        crs = src.crs
        transform = src.transform
        width = src.width
        height = src.height

    # Road network
    osm_filename = [f for f in os.listdir(osm_dir) if f.endswith('.gpkg')][0]
    osm_filename = os.path.join(osm_dir, osm_filename)
    dst_filename = os.path.join(output_dir, 'roadnetwork_speed.tif')
    modeling.rasterize_road_network(src_data=osm_filename,
                                    dst_filename=dst_filename,
                                    crs=crs,
                                    transform=transform,
                                    width=width,
                                    height=height,
                                    network_speeds=network_speeds)

    # Land cover
    dst_filename = os.path.join(output_dir, 'landcover_speed.tif')
    modeling.land_cover_speed(src_datadir=landcover_dir,
                              dst_filename=dst_filename,
                              crs=crs,
                              transform=transform,
                              width=width,
                              height=height,
                              landcover_speeds=landcover_speeds)
    return


def combine_speed_rasters(roadnetwork_speed, landcover_speed, dst_filename):
    """Combine both speed rasters. Road network speed takes priority."""
    with rasterio.open(roadnetwork_speed) as src:
        dst_profile = src.profile
        roadnetwork_speed = src.read(1)
    with rasterio.open(landcover_speed) as src:
        landcover_speed = src.read(1)
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config_file',
                        type=str,
                        help='.ini configuration file')
    args = parser.parse_args()
    conf = load_config(args.config_file)
    osm_dir = os.path.join(conf['DIRECTORIES']['InputDir'], 'openstreetmap')
    landcover_dir = conf['DIRECTORIES']['IntermDir']
    output_dir = conf['DIRECTORIES']['IntermDir']
    with open(conf['MODELING']['LandCoverSpeeds']) as f:
        landcover_speeds = json.load(f)
    with open(conf['MODELING']['RoadNetworkSpeeds']) as f:
        network_speeds = json.load(f)
    assign_speeds(osm_dir, landcover_dir, network_speeds, landcover_speeds, output_dir)
    
    


if __name__ == '__main__':
    main()