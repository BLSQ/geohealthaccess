"""Modeling accessibility."""

import json
import os
from pkg_resources import resource_filename

import numpy as np
import rasterio
from rasterio.crs import CRS
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


def speed_from_roads(src_filename, dst_filename, dst_transform, dst_crs,
                     dst_width, dst_height, network_speeds=None):
    """Convert network geometries to a raster with cell values equal
    to speed in km/h.

    Parameters
    ----------
    src_filename : str
        Path to input network geometries (with the following columns: geometry,
        highway, smoothness, tracktype and surface).
    dst_filename : str
        Path to output raster.
    dst_transform : Affine
        Affine transform of the output raster.
    dst_crs : dict
        CRS of the output raster.
    dst_width : int
        Output raster width.
    dst_height : int
        Output raster height.
    network_speeds : dict, optional
        Speeds associated to each OSM tag. If not provided,
        default values will be used.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    network = gpd.read_file(src_filename)
    network = network[network.geom_type == 'LineString']
    network.crs = CRS.from_epsg(4326)
    if network.crs != dst_crs:
        network = network.to_crs(dst_crs)

    shapes = []
    for _, row in network.iterrows():
        speed = get_segment_speed(row.highway, row.tracktype, row.smoothness,
                                  row.surface, network_speeds)
        if speed:
            shapes.append((row.geometry.__geo_interface__, int(speed)))

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
        nodata=255,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress='LZW')

    with rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        dst.write(speed_raster, 1)
    return dst_filename


def speed_from_landcover(src_filename, dst_filename, water_filename,
                         landcover_speeds=None):
    """Assign speed to each pixel in km/h based on the proportion
    of each land cover class in the cell. Each land cover class
    has a predefined speed value provided in the `landcover_speeds`
    dictionnary. 

    Parameters
    ----------
    src_filename : str
        Path to input land cover raster (multiband raster with one band
        per class, band descriptions with land cover label, and pixel
        values corresponding to land cover percentages.
    dst_filename : str
        Path to output raster.
    water_filename : str
        Path to surface water raster.
    landcover_speeds : dict, optional
        Speeds associated to each land cover category. If not provided,
        default values will be used.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    with rasterio.open(src_filename) as src:
        dst_profile = src.profile
        dst_profile.update(
            count=1,
            dtype=np.float32,
            nodata=-1)

    # Load default land cover speeds if not provided
    if not landcover_speeds:
        with open(resource_filename(__name__, 'resources/land-cover.json')) as f:
            landcover_speeds = json.load(f)

    with rasterio.open(dst_filename, 'w', **dst_profile) as dst, \
         rasterio.open(water_filename) as src_water, \
         rasterio.open(src_filename) as src_land:
        for ij, window in dst.block_windows(1):
            speed = np.zeros(shape=(window.height, window.width),
                             dtype=np.float32)
            for id, landcover in enumerate(src_land.descriptions, start=1):
                coverfraction = src_land.read(window=window, indexes=id)
                speed += (coverfraction / 100) * landcover_speeds[landcover]
            surface_water = src_water.read(window=window, indexes=1)
            speed[surface_water >= 2] = 0
            dst.write(speed, window=window, indexes=1)

    return dst_filename


def combine_speed_rasters(landcover_speed, roadnetwork_speed, dst_filename):
    """Combine land cover and road network speed rasters into a single GeoTIFF
    by keeping the max. speed value between both rasters.

    Parameters
    ----------
    landcover_speed : str
        Path to land cover speed raster.
    roadnetwork_speed : str
        Path to road network speed raster.
    dst_filename : str
        Path to output raster.
    
    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    with rasterio.open(landcover_speed) as src:
        dst_profile = src.profile
    with rasterio.open(landcover_speed) as src_land, \
         rasterio.open(roadnetwork_speed) as src_road, \
         rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        for ij, window in dst.block_windows(1):
            speed = np.maximum(src_land.read(window=window, indexes=1),
                               src_road.read(window=window, indexes=1))
            dst.write(speed, window=window, indexes=1)
    return dst_filename


def compute_friction(speed_raster, dst_filename, max_time=3600):
    """Convert speed raster to friction, i.e. time to cross a given pixel."""
    with rasterio.open(speed_raster) as src:
        dst_profile = src.profile
        xres, yres = abs(src.transform.a), abs(src.transform.e)
        dst_profile.update(dtype=np.float64)
    with rasterio.open(speed_raster) as src, \
         rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        for ij, window in dst.block_windows(1):
            speed = src.read(window=window, indexes=1).astype(np.float64)
            speed /= 3.6  # From km/hour to m/second
            diag_distance = np.sqrt(xres * xres + yres * yres)
            time_to_cross = distance / speed
            # Clean bad values
            time_to_cross[speed == 0] = max_time
            time_to_cross[np.isinf(time_to_cross)] = max_time
            time_to_cross[time_to_cross > max_time] = max_time
            dst.write(time_to_cross, window=window, indexes=1)
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


def add_surface_water(landcover_speed, surface_water, dst_file):
    """Use surface water raster to update land cover speeds.

    Parameters
    ----------
    landcover_speed : str
        Path to land cover speed raster.
    surface_water : str
        Path to surface water raster, with pixel values
        equal to the number of months with water cover.
    dst_file : str
        Path to output raster.
    
    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    pass


def combine_speeds(landcover, roadnetwork, dst_file):
    """Combine land cover and road network speeds into
    a single raster by keeping the max speed for each cell.

    Parameters
    ----------
    landcover : str
        Path to land cover speed raster.
    roadnetwork : str
        Path to road network speed raster.
    water : str
        Path to surface water raster.
    dst_file : str
        Output raster path.
    
    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    with rasterio.open(landcover) as src:
        dst_profile = src.profile
    # Use windowed read/write to save memory
    with rasterio.open(dst_file, 'w', **dst_profile) as dst:
        with rasterio.open(landcover) as src_landcover:
            for ji, window in src.block_windows(1):
                land_speed = src_landcover.read(1, window=window)
                with rasterio.open(roadnetwork) as src_road:
                    road_speed = src_road.read(1, window=window)
                dst.write(np.maximum(land_speed, road_speed),
                          window=window, indexes=1)
    return dst_file


def set_water_as_obstacle(speed, water, dst_file):
    """Assign null speed (obstacle) to surface water cells.

    Parameters
    ----------
    speed : str
        Path to speed raster.
    water : str
        Path to surface water raster.
    dst_file : str
        Path to output raster.
    
    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    with rasterio.open(speed) as src:
        dst_profile = src.profile
    # Use windowed read/write to save memory
    pass