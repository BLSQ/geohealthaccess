"""Modeling accessibility."""

import json
import os
from pkg_resources import resource_filename

import numpy as np
import rasterio
from rasterio.features import rasterize
import geopandas as gpd


def get_segment_speed(highway, tracktype=None, smoothness=None, surface=None,
                      network_speeds=None):
    """Get the speed (km/h) associated with a given road segment depending on
    various OpenStreetMap tags.

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
    network_speeds : dict, optional
        Speeds associated to each OSM tag. If not provided,
        default values will be used.
    
    Returns
    -------
    speed : float
        Speed in km/h.
    """
    # Use default network speeds if not provided
    if not network_speeds:
        json_file = resource_filename(__name__, 'resources/road-network.json')
        with open(json_file) as f:
            network_speeds = json.load(f)
    
    # Ignore unsupported road segments
    if highway not in network_speeds['highway']:
        return None

    # Get base speed and adjust depending on road quality
    base_speed = network_speeds['highway'][highway]
    tracktype = network_speeds['tracktype'].get(tracktype, 1)
    smoothness = network_speeds['smoothness'].get(smoothness, 1)
    surface = network_speeds['surface'].get(surface, 1)
    return base_speed * min(tracktype, smoothness, surface)


def rasterize_road_network(src_data, dst_filename, crs, transform,
                           width, height, network_speeds=None):
    """Convert network geometries to a raster with cell values equal
    to speed in km/h.

    Parameters
    ----------
    src_data : str
        Path to input network geometries (with the following columns: geometry,
        highway, smoothness, tracktype and surface).
    dst_filename : str
        Path to output raster.
    crs : dict
        CRS of the output raster.
    transform : Affine
        Affine transform of the output raster.
    width : int
        Output raster width.
    height : int
        Output raster height.
    network_speeds : dict, optional
        Speeds associated to each OSM tag. If not provided,
        default values will be used.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    network = gpd.read_file(src_data)
    network = network[network.geom_type == 'LineString']

    shapes = []
    for _, row in network.iterrows():
        speed = get_segment_speed(row.highway, row.tracktype, row.smoothness,
                                  row.surface, network_speeds)
        if speed:
            shapes.append((row.geometry.__geo_interface__, int(speed)))

    speed_raster = rasterize(
        shapes=shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        all_touched=True,
        dtype=rasterio.dtypes.uint8)

    dst_profile = rasterio.profiles.DefaultGTiffProfile()
    dst_profile.update(
        count=1,
        crs=crs,
        width=width,
        height=height,
        transform=transform,
        dtype=rasterio.dtypes.uint8,
        nodata=255)

    with rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        dst.write(speed_raster, 1)
    return dst_filename


def land_cover_speed(src_datadir, dst_filename, crs, transform,
                     width, height, landcover_speeds=None):
    """Assign speed in km/h based on land cover classes.
    
    Parameters
    ----------
    src_datadir : str
        Directory containing land cover layers.
    dst_filename : str
        Path to output raster.
    crs : dict
        CRS of the output raster.
    transform : Affine
        Affine transform of the output raster.
    width : int
        Output raster width.
    height : int
        Output raster height.
    landcover_speeds : dict, optional
        Speeds associated to each land cover category. If not provided,
        default values will be used.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    layers = []
    for fname in os.listdir(src_datadir):
        if 'landcover' in fname and fname.endswith('.tif'):
            layers.append(os.path.join(src_datadir, fname))

    with rasterio.open(layers[0]) as src:
        nodata = src.nodata
        dst_profile = src.profile
        dst_profile.update(dtype=np.float32, nodata=-1)
        speed_raster = np.zeros(shape=(src.height, src.width), dtype=np.float32)

    if not landcover_speeds:
        with open(resource_filename(__name__, 'resources/land-cover.json')) as f:
            landcover_speeds = json.load(f)
    
    for layer in layers:
        name, _ = os.path.basename(layer).split('.')
        land_cover = name.split('_')[1]
        with rasterio.open(layer) as src:
            coverfraction = src.read(1)
            speed_raster += (coverfraction / 100) * landcover_speeds[land_cover]

    speed_raster[coverfraction == nodata] = -1

    with rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        dst.write(speed_raster, 1)
    return dst_filename
