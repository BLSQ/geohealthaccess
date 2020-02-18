"""Modeling accessibility."""

import json
import os
import shutil

import geopandas as gpd
import numpy as np
import rasterio
from pkg_resources import resource_filename
from rasterio.crs import CRS
from rasterio.features import rasterize

from geohealthaccess import grasshelper
from geohealthaccess.grasshelper import gscript


def get_segment_speed(highway, tracktype=None, smoothness=None, surface=None,
                      network_speeds=None):
    """Get the speed (km/h) associated with a given road segment depending on
    various OpenStreetMap tags.
    final_speed = base_speed * max(smoothness, surface, tracktype),
    where base_speed is the speed associated with the OSM `highway`
    property, and `smoothness`, `surface` and `tracktype` the adjusting
    factor (between 0 and 1) associated with the respective OSM
    property.

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
    if os.path.isfile(dst_filename):
        return dst_filename
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
    if os.path.isfile(dst_filename):
        return dst_filename
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
        for _, window in dst.block_windows(1):
            speed = np.zeros(shape=(window.height, window.width),
                             dtype=np.float32)
            for id, landcover in enumerate(src_land.descriptions, start=1):
                coverfraction = src_land.read(window=window, indexes=id)
                speed += (coverfraction / 100) * landcover_speeds[landcover]
            surface_water = src_water.read(window=window, indexes=1)
            speed[surface_water >= 2] = 0
            dst.write(speed, window=window, indexes=1)

    return dst_filename


def combined_speed(landcover_speed, roads_speed, dst_filename, mode='car',
                   bike_basespeed=15, walk_basespeed=5):
    """Compute per-cell max. speed (in km/h) depending on the transport mode,
    i.e. 'car', 'bike' or 'walk'. 
    
    Transport mode is encoded into the speed values by adding 1000 for walking,
    2000 for bicycling, and 3000 for cars. Car and bike transport switch to
    walking when no roads are available.    
    
    Parameters
    ----------
    landcover_speed : str
        Path to land cover speed raster, as computed by speed_from_landcover().
    roads_speed : str
        Path to roads speed raster, as computed by speed_from_roads().
    dst_filename : str
        Path to output speed raster.
    mode : str, optional
        Transport mode: 'car', 'bike' or 'walk'.
    bike_basespeed : int, optional
        Bicycling base speed in km/h.
    walk_basespeed : int, optional
        Walking base speed in km/h.
    
    Returns
    -------
    dst_filename : str
        Path to output speed raster.
    """
    with rasterio.open(landcover_speed) as src:
        dst_profile = src.profile
    dst_profile.update(dtype='int16', nodata=-1)

    # Check mode parameter
    if mode not in ('car', 'bike', 'walk'):
        raise ValueError('Unrecognized transport mode.')

    # Open source and destination raster datasets
    with rasterio.open(landcover_speed) as src_landcover, \
         rasterio.open(roads_speed) as src_roads, \
         rasterio.open(dst_filename, 'w', **dst_profile) as dst:

        # Iterate over raster block windows to use less memory
        for _, window in dst.block_windows(1):
            
            speed_landcover = src_landcover.read(window=window, indexes=1)
            speed_roads = src_roads.read(window=window, indexes=1)
            speed = np.maximum(speed_landcover, speed_roads)
            road = speed_roads > 0
            noroad = speed_roads == 0

            if mode == 'car':
                speed[road] = speed[road] + 3000
                speed[noroad] = speed[noroad] + 1000  #  No roads, walking

            if mode == 'bike':
                BIKE_BASESPEED = 15
                speed[road] = 2000 + BIKE_BASESPEED
                speed[noroad] = speed[noroad] + 1000  # No roads, walking
            
            if mode == 'walk':
                WALK_BASESPEED = 5
                speed[road] = 1000 + WALK_BASESPEED  # Walking (base speed)
                speed[noroad] = speed[noroad] + 1000
            
            # Update nodata values and write block to disk
            speed[np.isnan(speed_landcover)] = -1
            speed[np.isnan(speed_roads)] = -1
            speed[speed < 0] = -1
            dst.write(speed.astype(np.int16), window=window, indexes=1)

    return dst_filename


def compute_friction(speed_raster, dst_filename, max_time=3600):
    """Convert speed raster to friction, i.e. time to cross a given pixel.

    Parameters
    ----------
    speed_raster : str
        Path to speed raster, as computed by combined_speed().
    dst_filename : str
        Path to output raster.
    max_time : int, optional
        Max. friction value (seconds).

    Returns
    -------
    dst_filename : str
        Path to output raster.
    """
    with rasterio.open(speed_raster) as src:
        dst_profile = src.profile
        xres, yres = abs(src.transform.a), abs(src.transform.e)
        dst_profile.update(dtype=np.float64)
    with rasterio.open(speed_raster) as src, \
         rasterio.open(dst_filename, 'w', **dst_profile) as dst:
        for _, window in dst.block_windows(1):
            speed = src.read(window=window, indexes=1).astype(np.float64)
            speed /= 3.6  # From km/hour to m/second
            diag_distance = np.sqrt(xres * xres + yres * yres)
            time_to_cross = diag_distance / speed
            # Clean bad values
            time_to_cross[speed == 0] = max_time
            time_to_cross[np.isinf(time_to_cross)] = max_time
            time_to_cross[time_to_cross > max_time] = max_time
            dst.write(time_to_cross, window=window, indexes=1)
    return dst_filename


def _compute_traveltime(src_friction, src_elevation, src_target, dst_cost,
                       dst_nearest, dst_backlink=None, method='whitebox'):
    """DEPERECATED. Compute accessibility map (travel time in seconds) from friction surface,
    elevation and destination points. Travel time can be computed with 3
    different software solutions: (1) the `CostDistance` module from Whitebox,
    (2) the `r.cost` module from GRASS GIS, and (3) the `r.walk` module from
    GRASS GIS. Relevant documentation can be found here:
        * `CostDistance`: https://jblindsay.github.io/wbt_book/available_tools/gis_analysis_distance_tools.html#CostDistance
        * `r.cost`: https://grass.osgeo.org/grass78/manuals/r.cost.html
        * `r.walk`: https://grass.osgeo.org/grass78/manuals/r.walk.html
        * `r.walk.accessmod`: https://github.com/fxi/AccessMod_r.walk

    Parameters
    ----------
    src_friction : str
        Path to input friction raster.
    src_elevation : str
        Path to input elevation raster.
    src_target : str
        Path to input destination points.
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility
        map).
    dst_nearest : str
        Path to nearest entity raster (i.e. for each cell, the ID of the
        nearest destination point).
    dst_backlink : str
        Path to output backlink raster (movement directions).
    method : str, optional
        Method used to compute the travel times: `whitebox`, `r.cost` or
        `r.walk`. Defaults to `whitebox`.
    
    Returns
    -------
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility
        map).
    dst_nearest : str
        Path to nearest entity raster (i.e. for each cell, the ID of the
        nearest destination point).
    """
    MEMORY = 8000  # TODO: Determine best amount of memory to be used.
    if method not in ('whitebox', 'r.cost', 'r.walk'):
        raise ValueError(f'{method} is not a valid method.')
    
    # Create output dirs if needed
    for dst_file in (dst_cost, dst_nearest, dst_backlink):
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)

    if method == 'whitebox':
        import whitebox
        wbt = whitebox.WhiteboxTools()
        wbt.cost_distance(source=src_target,
                          cost=src_friction,
                          out_accum=dst_cost,
                          out_backlink=dst_backlink)
    
    if method.startswith('r.'):
        
        from geohealthaccess import grasshelper
        from geohealthaccess.grasshelper import gscript

        # Create temporary GRASSDATA directory
        dst_dir = os.path.dirname(dst_cost)
        grass_datadir = os.path.join(dst_dir, 'GRASSDATA')
        os.makedirs(grass_datadir)

        # Get source CRS and setup GRASS environment accordingly
        with rasterio.open(src_friction) as src:
            crs = src.crs
        grasshelper.setup_environment(grass_datadir, crs)

        # Load input raster data into the GRASS environment
        # NB: Data will be stored in `grass_datadir`.
        gscript.run_command('r.in.gdal',
                            input=src_friction,
                            output='friction',
                            overwrite=True)
        gscript.run_command('g.region', raster='friction')
        gscript.run_command('r.in.gdal',
                            input=src_elevation,
                            output='elevation',
                            overwrite=True)
        gscript.run_command('r.in.gdal',
                            input=src_target,
                            output='target',
                            overwrite=True)
        # In input point raster, ensure that all pixels
        # with value = 0 are assigned a null value.
        gscript.run_command('r.null',
                            map='target',
                            setnull=0)

        # Compute travel time with GRASS r.cost module
        if method == 'r.cost':
            gscript.run_command('r.cost',
                                overwrite=True,
                                input='friction',
                                output='cost',
                                outdir='backlink',
                                nearest='nearest',
                                start_raster='target',
                                memory=MEMORY)
        
        # Compute travel time with GRASS r.walk module
        if method == 'r.walk':
            gscript.run_command('r.walk',
                                elevation='elevation',
                                friction='friction',
                                output='cost',
                                outdir='backlink',
                                start_raster='target',
                                memory=MEMORY)
        
        # Save output data to disk
        GDAL_OPT = ['TILED=YES', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256',
                    'COMPRESS=LZW', 'PREDICTOR=2', 'NUM_THREADS=ALL_CPUS']
        gscript.run_command('r.out.gdal',
                            input='cost',
                            output=dst_cost,
                            format='GTiff',
                            type='Int32',
                            createopt=','.join(GDAL_OPT),
                            nodata=-1)
        gscript.run_command('r.out.gdal',
                            input='backlink',
                            output=dst_backlink,
                            format='GTiff',
                            createopt=','.join(GDAL_OPT))
        if method == 'r.cost':
            # Only available with `r.cost` module
            gscript.run_command('r.out.gdal',
                                input='nearest',
                                output=dst_nearest,
                                format='GTiff',
                                createopt=','.join(GDAL_OPT))
        
        # Clean GRASSDATA directory
        shutil.rmtree(grass_datadir)    
    
    return


def r_walk_accessmod(src_speed, src_elevation, src_target, dst_cost,
                     dst_backlink, max_memory=8000):
    """Compute accessibility map (travel time in seconds) from friction
    surface, elevation and destination points.
    
    Travel time is computed using the r.walk modification by AccessMod:
    * `r.walk`: https://grass.osgeo.org/grass78/manuals/r.walk.html
    * `r.walk.accessmod`: https://github.com/fxi/AccessMod_r.walk
    NB: Only works with GRASS 7.2 for now.

    Parameters
    ----------
    src_speed : str
        Path to input speed raster.
    src_elevation : str
        Path to input elevation raster.
    src_target : str
        Path to input destination points.
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_backlink : str
        Path to output backlink raster (movement directions).
    max_memory : int, optional
        Max. memory used by the GRASS module (MB). Default = 8000 MB.

    Returns
    -------
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster (i.e. for each cell, the ID of
        the nearest destination point).
    """
    # Create output dirs if needed
    for dst_file in (dst_cost, dst_backlink):
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
    
    # Create temporary GRASSDATA directory
    dst_dir = os.path.dirname(dst_cost)
    grass_datadir = os.path.join(dst_dir, 'GRASSDATA')
    if os.path.isdir(grass_datadir):
        shutil.rmtree(grass_datadir)
    os.makedirs(grass_datadir)

    # Get source CRS and setup GRASS environment accordingly
    with rasterio.open(src_speed) as src:
        crs = src.crs
    grasshelper.setup_environment(grass_datadir, crs)

    # Load input raster data into the GRASS environment
    # NB: Data will be stored in `grass_datadir`.
    gscript.run_command('r.in.gdal',
                        input=src_speed,
                        output='speed',
                        overwrite=True)
    gscript.run_command('g.region', raster='speed')
    gscript.run_command('r.in.gdal',
                        input=src_elevation,
                        output='elevation',
                        overwrite=True)
    gscript.run_command('r.in.gdal',
                        input=src_target,
                        output='target',
                        overwrite=True)
    # In input point raster, ensure that all pixels
    # with value = 0 are assigned a null value.
    gscript.run_command('r.null',
                        map='target',
                        setnull=0)
    
    # Compute travel time with GRASS r.walk.accessmod
    gscript.run_command('r.walk.accessmod',
                        flags='s',
                        elevation='elevation',
                        friction='speed',
                        output='cost',
                        # nearest='nearest',
                        outdir='backlink',
                        start_raster='target',
                        memory=max_memory)
    
    # Save output data to disk
    GDAL_OPT = ['TILED=YES', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256',
                'COMPRESS=LZW', 'NUM_THREADS=ALL_CPUS']
    gscript.run_command('r.out.gdal',
                        input='cost',
                        output=dst_cost,
                        format='GTiff',
                        type='Float64',
                        createopt=','.join(GDAL_OPT),
                        nodata=-1)
    gscript.run_command('r.out.gdal',
                        input='backlink',
                        output=dst_backlink,
                        format='GTiff',
                        createopt=','.join(GDAL_OPT),
                        nodata=-1)

    # Clean GRASSDATA directory
    shutil.rmtree(grass_datadir)

    return dst_cost, dst_backlink
