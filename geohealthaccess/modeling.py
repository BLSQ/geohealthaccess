"""Modeling accessibility."""

import json
import os
from tempfile import TemporaryDirectory
import shutil

import geopandas as gpd
from loguru import logger
import pandas as pd
import numpy as np
import rasterio
from rasterio.crs import CRS
from pkg_resources import resource_filename
from rasterio.features import rasterize

from geohealthaccess import grasshelper
from geohealthaccess.grasshelper import grass_execute, log_cmd_output
from geohealthaccess.preprocessing import default_compression, GDAL_CO
from geohealthaccess.grasshelper import gscript


logger.disable("__name__")


def default_landcover_speeds():
    """Get default speeds associated with land cover catagories.

    Returns
    -------
    dict
        Default land cover speeds.
    """
    with open(resource_filename(__name__, "resources/travel-speeds.json")) as f:
        return json.load(f).get("land-cover")


def default_transport_speeds():
    """Get default speeds associated with transport network type.

    Returns
    -------
    dict
        Default transport network speeds.
    """
    with open(resource_filename(__name__, "resources/travel-speeds.json")) as f:
        return json.load(f).get("transport")


def get_segment_speed(
    highway, tracktype=None, smoothness=None, surface=None, speeds=None
):
    """Get the speed (km/h) associated with a given road segment.

    Speed value depends on various OpenStreetMap tags according to the following
    formula: `base_speed x max(smoothness, surface, tracktype)`, where
    base_speed is the speed associated with the OSM `highway` property, and
    `smoothness`, `surface` and `tracktype` the adjusting factor (between 0 and
    1) associated with the respective OSM property.

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
    speeds : dict, optional
        Speeds associated to each OSM tag. If not provided,
        default values will be used.

    Returns
    -------
    speed : float
        Speed in km/h.
    """
    # Use default network speeds if not provided
    if not speeds:
        logger.info("Transport network speeds not provided. Using default values.")
        speeds = default_transport_speeds()

    # Ignore unsupported road segments
    if highway not in speeds["highway"]:
        return None

    # Get base speed and adjust depending on road quality
    base_speed = speeds["highway"][highway]
    tracktype = speeds["tracktype"].get(tracktype, 1)
    smoothness = speeds["smoothness"].get(smoothness, 1)
    surface = speeds["surface"].get(surface, 1)
    return base_speed * min(tracktype, smoothness, surface)


def speed_from_roads(
    src_roads,
    dst_file,
    dst_transform,
    dst_crs,
    dst_width,
    dst_height,
    src_ferry=None,
    speeds=None,
    overwrite=False,
):
    """Convert network geometries to a raster with travel speed as cell values.

    Parameters
    ----------
    src_roads : str
        Path to input network geometries (with the following columns: geometry,
        highway, smoothness, tracktype and surface).
    dst_file : str
        Path to output raster.
    dst_transform : Affine
        Affine transform of the output raster.
    dst_crs : dict
        CRS of the output raster.
    dst_width : int
        Output raster width.
    dst_height : int
        Output raster height.
    src_ferry : str, optional
        Path to ferry routes data from OSM.
    speeds : dict, optional
        Speeds associated to each OSM tag. If not provided,
        default values will be used.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info("Creating travel speeds raster from the road network.")
    if os.path.isfile(dst_file) and not overwrite:
        logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
        return dst_file
    if not speeds:
        logger.info("No land cover speeds provided. Using default values.")
        speeds = default_landcover_speeds()

    # Raster profile
    dst_profile = rasterio.default_gtiff_profile
    dst_profile.update(
        count=1,
        transform=dst_transform,
        crs=dst_crs,
        width=dst_width,
        height=dst_height,
        dtype="float32",
        nodata=-9999,
        **default_compression("float32"),
    )

    network = gpd.read_file(src_roads)
    if src_ferry:
        ferry = gpd.read_file(src_ferry)
        network = pd.concat((network, ferry))
    network = network.to_crs(dst_crs)

    # Get shapes and speed values of road segments
    shapes = []
    for _, row in network.iterrows():
        speed = get_segment_speed(
            row.highway, row.tracktype, row.smoothness, row.surface, speeds
        )
        if speed:
            shapes.append((row.geometry.__geo_interface__, speed))

    # Add ferry routes if needed
    if src_ferry:
        ferry = gpd.read_file(src_ferry)
        speed = speeds["route"]["ferry"]
        shapes += [(geom.__geo_interface__, speed) for geom in ferry.geometry]

    speed_raster = rasterize(
        shapes=shapes,
        out_shape=(dst_height, dst_width),
        transform=dst_transform,
        fill=0,
        all_touched=True,
        dtype="float32",
    )
    logger.info(f"{len(shapes)} transport network segments rasterized.")

    with rasterio.open(dst_file, "w", **dst_profile) as dst:
        dst.write(speed_raster, 1)

    logger.info(
        f"Transport network travel speeds saved as `{os.path.basename(dst_file)}`."
    )

    return dst_file


def speed_from_landcover(src_landcover, dst_file, speeds=None, overwrite=False):
    """Create travel speed raster from land cover.

    Assign speed in km/h to each raster cell based on its land cover category.
    Speed values are provided from the `speeds` dictionnary.

    Parameters
    ----------
    src_landcover : str
        Path to input land cover raster (multiband raster with one band
        per class, band descriptions with land cover label, and pixel
        values corresponding to land cover percentages.
    dst_file : str
        Path to output raster.
    speeds : dict, optional
        Speeds associated to each land cover category.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info("Creating travel speeds raster from land cover.")
    if os.path.isfile(dst_file) and not overwrite:
        logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
        return dst_file
    if not speeds:
        logger.info("No land cover speeds provided. Using default values.")
        speeds = default_landcover_speeds()
    with rasterio.open(src_landcover) as src:
        dst_profile = src.profile.copy()
        dst_profile.update(
            count=1, dtype="float32", nodata=-9999, **default_compression("float32")
        )

    with rasterio.open(src_landcover) as src, rasterio.open(
        dst_file, "w", **dst_profile
    ) as dst:
        for _, window in dst.block_windows(1):
            speed = np.zeros(shape=(window.height, window.width), dtype=np.float32)
            for id, landcover in enumerate(src.descriptions, start=1):
                coverfraction = src.read(window=window, indexes=id)
                speed += (coverfraction / 100.0) * speeds[landcover]
                speed[coverfraction == src.nodata] = 0
            speed[speed < 0] = -9999
            dst.write(speed, window=window, indexes=1)

    logger.info(f"Land cover travel speeds saved as `{os.path.basename(dst_file)}`.")

    return dst_file


def travel_obstacles(src_water, src_slope, dst_file, max_slope=30, overwrite=False):
    """Compute obstacle raster from water and slope data.

    Positive cells in `src_water` and cells with a slope superior or
    equal to `max_slope` are considered obstacles. Output raster is an
    uint8 geotiff with 0 for non-obstacle cells, 1 for obstacle cells,
    and 255 for nodata.

    Parameters
    ----------
    src_water : str or list of str
        Input water raster with positive values for water cells. If multiple
        rasters are provided, they are merged using a maximum aggregate function.
    src_slope : str
        Input slope raster in degrees.
    dst_file : str
        Path to output raster.
    max_slope : float, optional
        Slope threshold in degrees (default=30°).
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    str
        Path to output raster.
    """
    logger.info("Creating obstacle raster from water and slope.")
    if os.path.isfile(dst_file) and not overwrite:
        logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
        return dst_file

    # Convert src_water to a list if a single raster is provided
    if not isinstance(src_water, list) and not isinstance(src_water, tuple):
        src_water = [src_water]

    # Get raster profile information
    with rasterio.open(src_water[0]) as src:
        dst_profile = src.profile
        nrows, ncols = src.height, src.width
        dst_profile.update(dtype="uint8", nodata=255, **default_compression("uint8"))

    obstacle = np.zeros(shape=(nrows, ncols), dtype=np.uint8)
    for water in src_water:
        logger.info(
            f"Setting water pixels from {os.path.basename(water)} as obstacles."
        )
        with rasterio.open(water) as src:
            obstacle[src.read(1) > 0] = 1
    with rasterio.open(src_slope) as src:
        logger.info(f"Setting slope pixels > {max_slope}° as obstacles.")
        obstacle[src.read(1) >= max_slope] = 1
    with rasterio.open(dst_file, "w", **dst_profile) as dst:
        dst.write(obstacle, 1)
    logger.info(
        f"Computed obstacle raster ({np.count_nonzero(obstacle)} obstacle pixels)."
    )
    return dst_file


def combine_speed(
    landcover,
    transport,
    obstacle,
    dst_file,
    mode="car",
    walk_basespeed=5,
    bike_basespeed=15,
):
    """Compute per-cell max. speed (km/h) depending on transport mode.

    Parameters
    ----------
    landcover : str
        Path to land cover speed raster, as computed by `speed_from_landcover()`.
    transport : str
        Path to transport network speed raster, as computed by
        `speed_from_roads()`.
    obstacle : str
        Path to obstacle raster, as computed by `travel_obstacles()`.
    dst_file : str
        Path to output speed raster.
    mode : str, optional
        Transport mode: 'car', 'bike' or 'walk'.
    bike_basespeed : int, optional
        Bicycling base speed in km/h on a flat surface. Default=15.
    walk_basespeed : int, optional
        Walking base speed in km/h on a flat surface. Default=5.

    Returns
    -------
    dst_file : str
        Path to output speed raster.
    """
    logger.info(f"Combining travel speeds rasters for `{mode}` transport mode.")
    with rasterio.open(landcover) as src:
        dst_profile = src.profile
    dst_profile.update(dtype="float32", nodata=-9999, **default_compression("float32"))

    # Check mode parameter
    if mode not in ("car", "bike", "walk"):
        raise ValueError("Unrecognized transport mode.")

    with rasterio.open(landcover) as srcland, rasterio.open(
        transport
    ) as srcnet, rasterio.open(obstacle) as srcobs, rasterio.open(
        dst_file, "w", **dst_profile
    ) as dst:
        for _, window in dst.block_windows(1):
            speed_landcover = srcland.read(window=window, indexes=1)
            speed_roads = srcnet.read(window=window, indexes=1)
            obstacle = srcobs.read(window=window, indexes=1)
            speed_landcover[obstacle == 1] = 0
            speed = np.maximum(speed_landcover, speed_roads)

            on_road = speed_roads > 0
            if mode == "bike":
                speed[on_road] = bike_basespeed
            if mode == "walk":
                speed[on_road] = walk_basespeed

            # Update nodata values and write block to disk
            speed[np.isnan(speed_landcover)] = -9999
            speed[np.isnan(speed_roads)] = -9999
            speed[speed < 0] = -9999
            dst.write(speed.astype(np.float32), window=window, indexes=1)

    return dst_file


def compute_friction(speed_raster, dst_file, max_time=3600, one_meter=False):
    """Convert speed raster to friction, i.e. time to cross a given pixel.

    Parameters
    ----------
    speed_raster : str
        Path to speed raster, as computed by `combine_speed()`.
    dst_file : str
        Path to output raster.
    max_time : int, optional
        Max. friction value (seconds).
    one_meter : bool, optional
        Compute time to cross one meter instead of one pixel.

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info(f"Computing friction surface from `{os.path.basename(speed_raster)}`.")
    with rasterio.open(speed_raster) as src:
        dst_profile = src.profile
        xres = abs(src.transform.a)
        dst_profile.update(
            dtype="float64", nodata=-9999, **default_compression("float64")
        )
    with rasterio.open(speed_raster) as src, rasterio.open(
        dst_file, "w", **dst_profile
    ) as dst:
        for _, window in dst.block_windows(1):
            speed = src.read(window=window, indexes=1).astype(np.float64)
            speed /= 3.6  # From km/hour to m/second
            nonzero = speed != 0
            time_to_cross = np.zeros_like(speed, dtype="float64")
            if one_meter:
                # Time to cross one meter
                time_to_cross[nonzero] = 1 / speed[nonzero]
            else:
                # Time to cross one pixel
                time_to_cross[nonzero] = xres / speed[nonzero]
            # Clean bad values
            time_to_cross[speed == 0] = -9999
            time_to_cross[np.isnan(time_to_cross)] = -9999
            time_to_cross[np.isinf(time_to_cross)] = -9999
            time_to_cross[time_to_cross >= max_time] = -9999
            dst.write(time_to_cross, window=window, indexes=1)
    return dst_file


def rasterize_destinations(
    src_features,
    dst_file,
    dst_transform,
    dst_crs,
    dst_height,
    dst_width,
    overwrite=False,
):
    """Rasterize input destination features.

    Parameters
    ----------
    src_features : str
        Path to input destination features (.geojson or .gpkg).
    dst_file : str
        Path to output geotiff file.
    dst_transform : Affine
        Target raster transform.
    dst_crs : CRS
        Target raster CRS.
    dst_height : int
        Target raster height.
    dst_width : int
        Target raster width.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    dst_file : str
        Path to output raster.
    """
    logger.info(
        f"Rasterizing destination points from `{os.path.basename(src_features)}`."
    )
    if os.path.isfile(dst_file) and not overwrite:
        logger.info(f"{os.path.basename(dst_file)} already exists. Skipping.")
        return dst_file

    # Load source features as geodataframe and reproject geometries if needed
    features = gpd.read_file(src_features)
    if not features.crs:
        features.crs = CRS.from_epsg(4326)
    if features.crs != dst_crs:
        features = features.to_crs(dst_crs)

    shapes = [(g.__geo_interface__, i + 1) for i, g in enumerate(features.geometry)]
    raster = rasterize(
        shapes=shapes,
        transform=dst_transform,
        out_shape=(dst_height, dst_width),
        all_touched=True,
        fill=0,
        dtype="int16",
    )

    dst_profile = rasterio.default_gtiff_profile
    dst_profile.update(
        count=1,
        dtype="int16",
        nodata=-32768,
        transform=dst_transform,
        crs=dst_crs,
        width=dst_width,
        height=dst_height,
        **default_compression("int16"),
    )

    with rasterio.open(dst_file, "w", **dst_profile) as dst:
        dst.write(raster, 1)
    logger.info(f"{len(shapes)} destination points rasterized.")

    return dst_file


def anisotropic_costdistance(
    src_friction,
    src_target,
    src_elevation,
    dst_cost,
    dst_nearest,
    dst_backlink,
    extent=None,
    max_memory=8000,
):
    """Compute accessibility map (travel time in seconds) from friction
    surface, topography and destination points.

    Travel time is computed using the `r.walk` GRASS module
    ('<https://grass.osgeo.org/grass78/manuals/r.walk.html>`_).
    Topography is used to perform an anisotropic analysis of
    travel time, i.e. cost of moving downhill and uphill.
    Only relevant for pedestrian models for now, since
    anisotropic costs when bicycling require different formula
    parameters, and motorized vehicles are not as much influenced
    by slope gradients.

    Parameters
    ----------
    src_friction : str
        Path to input friction surface raster (seconds).
    src_target : str
        Path to input destination points.
    src_elevation : str
        Path to input elevation raster (meters).
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster.
    dst_backlink : str
        Path to output backlink raster (movement directions).
    extent : shapely geometry, optional
        Limit analysis to a given extent provided as a shapely geometry.
        By default, extent is set to match input rasters.
    max_memory : int, optional
        Max. memory used by the GRASS module (MB). Default = 8000 MB.

    Returns
    -------
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster.
    dst_nearest : str
        Path to output nearest entity raster (i.e. for each cell, the ID of
        the nearest destination point).
    """
    # Create output dirs if needed
    for dst_file in (dst_cost, dst_nearest, dst_backlink):
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)

    # Create temporary GRASSDATA directory
    dst_dir = os.path.dirname(dst_cost)
    grass_datadir = os.path.join(dst_dir, "GRASSDATA")
    if os.path.isdir(grass_datadir):
        shutil.rmtree(grass_datadir)
    os.makedirs(grass_datadir)

    # Get source CRS and setup GRASS environment accordingly
    with rasterio.open(src_friction) as src:
        crs = src.crs
    grasshelper.setup_environment(grass_datadir, crs)

    # Load input raster data into the GRASS environment
    # NB: Data will be stored in `grass_datadir`.
    grass_execute(
        "r.in.gdal", input=src_friction, output="friction", overwrite=True, quiet=True
    )

    # Set computational region
    cmd_output = grass_execute("g.region", raster="friction")
    log_cmd_output(cmd_output)
    if extent:
        west, south, east, north = extent.bounds
        cmd_output = grass_execute(
            "g.region",
            flags="a",  # Align with initial resolution
            n=north,
            e=east,
            s=south,
            w=west,
        )
        log_cmd_output(cmd_output)

    cmd_output = grass_execute(
        "r.in.gdal", input=src_target, output="target", overwrite=True,
    )
    log_cmd_output(cmd_output)
    cmd_output = grass_execute(
        "r.in.gdal", input=src_elevation, output="elevation", overwrite=True,
    )
    log_cmd_output(cmd_output)
    # In input point raster, ensure that all pixels
    # with value = 0 are assigned a null value.
    cmd_output = grass_execute("r.null", map="target", setnull=0)
    log_cmd_output(cmd_output)

    # Compute travel time with GRASS r.walk.accessmod
    cmd_output = grass_execute(
        "r.walk",
        flags="kn",
        friction="friction",
        elevation="elevation",
        output="cost",
        nearest="nearest",
        outdir="backlink",
        start_raster="target",
        memory=max_memory,
    )
    log_cmd_output(cmd_output)

    # Save output data to disk
    cmd_output = grass_execute(
        "r.out.gdal",
        input="cost",
        output=dst_cost,
        format="GTiff",
        type="Float64",
        createopt=",".join(GDAL_CO).replace("PREDICTOR=2", "PREDICTOR=3"),
        nodata=-1,
    )
    log_cmd_output(cmd_output)
    cmd_output = grass_execute(
        "r.out.gdal",
        input="backlink",
        output=dst_backlink,
        format="GTiff",
        createopt=",".join(GDAL_CO),
        nodata=-1,
    )
    log_cmd_output(cmd_output)
    cmd_output = grass_execute(
        "r.out.gdal",
        input="nearest",
        output=dst_nearest,
        format="GTiff",
        createopt=",".join(GDAL_CO),
    )
    log_cmd_output(cmd_output)

    # Clean GRASSDATA directory
    shutil.rmtree(grass_datadir)

    return dst_cost, dst_nearest, dst_backlink


def isotropic_costdistance(
    src_friction,
    src_target,
    dst_cost,
    dst_nearest,
    dst_backlink,
    extent=None,
    max_memory=8000,
    overwrite=False,
):
    """Compute accessibility map (travel time in seconds) from friction
    surface and destination points.

    Travel time is computed using the `r.cost` GRASS module
    (`<https://grass.osgeo.org/grass78/manuals/r.cost.html>`_).
    Cost of moving downhill or uphill is not taken into account.

    Parameters
    ----------
    src_friction : str
        Path to input friction surface raster (seconds).
    src_target : str
        Path to input destination points.
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster.
    dst_backlink : str
        Path to output backlink raster (movement directions).
    extent : shapely geometry, optional
        Limit analysis to a given extent provided as a shapely geometry.
        By default, extent is set to match input rasters.
    max_memory : int, optional
        Max. memory used by the GRASS module (MB). Default = 8000 MB.
    overwrite : bool, optional
        Overwrite existing files.

    Returns
    -------
    dst_cost : str
        Path to output accumulated cost raster (i.e. the accessibility map).
    dst_nearest : str
        Path to output nearest entity raster.
    dst_nearest : str
        Path to output nearest entity raster (i.e. for each cell, the ID of
        the nearest destination point).
    """
    # Create output dirs if needed
    for dst_file in (dst_cost, dst_nearest, dst_backlink):
        os.makedirs(os.path.dirname(dst_file), exist_ok=True)

    # Create temporary GRASSDATA directory
    dst_dir = os.path.dirname(dst_cost)
    grass_datadir = os.path.join(dst_dir, "GRASSDATA")
    if os.path.isdir(grass_datadir):
        shutil.rmtree(grass_datadir)
    os.makedirs(grass_datadir)

    # Get source CRS and setup GRASS environment accordingly
    with rasterio.open(src_friction) as src:
        crs = src.crs
    grasshelper.setup_environment(grass_datadir, crs)

    # Load input raster data into the GRASS environment
    # NB: Data will be stored in `grass_datadir`.
    cmd_output = grass_execute(
        "r.in.gdal", input=src_friction, output="friction", overwrite=True,
    )
    log_cmd_output(cmd_output)

    # Set computational region
    cmd_output = gscript.read_command("g.region", raster="friction")
    log_cmd_output(cmd_output)
    if extent:
        west, south, east, north = extent.bounds
        cmd_output = gscript.read_command(
            "g.region",
            flags="a",  # Align with initial resolution
            n=north,
            e=east,
            s=south,
            w=west,
        )
        log_cmd_output(cmd_output)

    cmd_output = gscript.read_command(
        "r.in.gdal",
        input=src_target,
        output="target",
        quiet=True,
        superquiet=True,
        overwrite=True,
    )
    log_cmd_output(cmd_output)

    # In input point raster, ensure that all pixels
    # with value = 0 are assigned a null value.
    cmd_output = grass_execute("r.null", map="target", setnull=0)
    log_cmd_output(cmd_output)

    # Compute travel time with GRASS r.walk.accessmod
    cmd_output = grass_execute(
        "r.cost",
        flags="kn",
        input="friction",
        output="cost",
        nearest="nearest",
        outdir="backlink",
        start_raster="target",
        memory=max_memory,
    )
    log_cmd_output(cmd_output)

    # Save output data to disk
    cmd_output = grass_execute(
        "r.out.gdal",
        input="cost",
        output=dst_cost,
        format="GTiff",
        type="Float64",
        createopt=",".join(GDAL_CO).replace("PREDICTOR=2", "PREDICTOR=3"),
        nodata=-1,
    )
    log_cmd_output(cmd_output)
    cmd_output = grass_execute(
        "r.out.gdal",
        input="backlink",
        output=dst_backlink,
        format="GTiff",
        createopt=",".join(GDAL_CO),
        nodata=-1,
    )
    log_cmd_output(cmd_output)
    cmd_output = grass_execute(
        "r.out.gdal",
        input="nearest",
        output=dst_nearest,
        format="GTiff",
        createopt=",".join(GDAL_CO),
    )
    log_cmd_output(cmd_output)

    # Clean GRASSDATA directory
    shutil.rmtree(grass_datadir)

    return dst_cost, dst_nearest, dst_backlink


def seconds_to_minutes(src_raster):
    """Convert travel times from seconds to minutes.

    Parameters
    ----------
    src_raster : str
        Path to raster to convert.
    """
    logger.info(f"Converting {os.path.basename(src_raster)} from seconds to minutes.")
    with rasterio.open(src_raster) as src:
        dst_profile = src.profile
        dst_profile.update(**default_compression(src.dtypes[0]), nodata=-9999)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:
        tmpfile = os.path.join(tmpdir, "converted.tif")

        with rasterio.open(tmpfile, "w", **dst_profile) as dst, rasterio.open(
            src_raster
        ) as src:
            for _, window in dst.block_windows(1):
                seconds = src.read(window=window, indexes=1)
                minutes = seconds / 60
                minutes[seconds < 0] = dst_profile.get("nodata")
                dst.write(minutes, window=window, indexes=1)

        shutil.copyfile(tmpfile, src_raster)
