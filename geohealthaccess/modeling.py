"""Modeling accessibility."""

import json
from pkg_resources import resource_filename

import rasterio
from rasterio.features import rasterize
import geopandas as gpd


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
