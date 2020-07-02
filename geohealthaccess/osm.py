"""Processing of OpenStreetMap data.

The module provides functions to work with .osm.pbf files.
`Osmium <https://osmcode.org/osmium-tool/>`_ is required for most of them.
"""

import os
from subprocess import run, PIPE, DEVNULL
import logging
import tempfile
import functools

import numpy as np
import rasterio
from rasterio.features import rasterize
import geopandas as gpd

from geohealthaccess.preprocessing import default_compression
from geohealthaccess.errors import OsmiumNotFoundError, MissingDataError
from geohealthaccess.utils import human_readable_size

log = logging.getLogger(__name__)


def requires_osmium(func):
    """Check that osmium is available on the system."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            run(["osmium"], stdout=DEVNULL, stderr=DEVNULL)
        except FileNotFoundError:
            raise OsmiumNotFoundError("Osmium not found.")
        return func(*args, **kwargs)

    return wrapper


@requires_osmium
def tags_filter(osm_pbf, dst_fname, expression, overwrite=True):
    """Extract OSM objects based on their tags.

    The function reads an input .osm.pbf file and uses `osmium tags-filter`
    to extract the relevant objects into an output .osm.pbf file.

    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    dst_fname : str
        Path to output .osm.pbf file.
    expression : str
        Osmium tags-filter expression. See `osmium tags-filter` manpage for details.
    overwrite : bool, optional
        Overwrite existing file.

    Returns
    -------
    dst_fname : str
        Path to output .osm.pbf file.
    """
    expression_parts = expression.split(" ")
    command = ["osmium", "tags-filter", osm_pbf]
    command += expression_parts
    command += ["-o", dst_fname]
    if overwrite:
        command += ["--overwrite"]
    log.info(f"Running command: {' '.join(command)}")
    run(command, check=True, stdout=DEVNULL, stderr=DEVNULL)
    src_size = human_readable_size(os.path.getsize(osm_pbf))
    dst_size = human_readable_size(os.path.getsize(dst_fname))
    log.info(
        f"Extracted {os.path.basename(dst_fname)} ({dst_size}) "
        f"from {os.path.basename(osm_pbf)} ({src_size})."
    )
    return dst_fname


@requires_osmium
def to_geojson(osm_pbf, dst_fname, overwrite=True):
    """Convert an input .osm.pbf file to a GeoJSON file.

    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    dst_fname : str
        Path to output .osm.pbf file.
    overwrite : bool, optional
        Overwrite existing file.

    Returns
    -------
    dst_fname : str
        Path to output GeoJSON file.
    """
    command = ["osmium", "export", osm_pbf, "-o", dst_fname]
    if overwrite:
        command += ["--overwrite"]
    log.info(f"Running command: {' '.join(command)}")
    run(command, check=True, stdout=DEVNULL, stderr=DEVNULL)
    src_size = human_readable_size(os.path.getsize(osm_pbf))
    dst_size = human_readable_size(os.path.getsize(dst_fname))
    log.info(
        f"Created {os.path.basename(dst_fname)} ({dst_size}) "
        f"from {os.path.basename(osm_pbf)} ({src_size})."
    )
    return dst_fname


# Osmium tags-filter expression and properties of interest for each supported
# thematic extract.
EXTRACTS = {
    "roads": {
        "expression": "w/highway",
        "properties": ["highway", "smoothness", "surface", "tracktype"],
        "geom_types": ["LineString"],
    },
    "water": {
        "expression": "nwr/natural=water nwr/waterway nwr/water",
        "properties": ["waterway", "natural", "water", "wetland", "boat"],
        "geom_types": ["LineString", "Polygon", "MultiPolygon"],
    },
    "health": {
        "expression": "nwr/amenity=clinic,doctors,hospital,pharmacy nwr/healthcare",
        "properties": ["amenity", "name", "healthcare", "dispensing", "description"],
        "geom_types": ["Point"],
    },
    "ferry": {
        "expression": "w/route=ferry",
        "properties": [
            "route",
            "duration",
            "motor_vehicle",
            "motorcar",
            "motorcycle",
            "bicycle",
            "foot",
        ],
        "geom_types": ["LineString"],
    },
}


def _centroid(geom):
    """Get centroid if possible."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom.centroid
    return geom


def _filter_columns(geodataframe, valid_columns):
    """Filter columns of a given geodataframe."""
    n_removed = 0
    for column in geodataframe.columns:
        if column not in valid_columns and column != "geometry":
            geodataframe = geodataframe.drop([column], axis=1)
            n_removed += 1
    log.info(f"Removed {n_removed} columns. {len(geodataframe.columns)} remaining.")
    return geodataframe


def _count_objects(osm_pbf):
    """Count objects of each type in an .osm.pbf file."""
    p = run(["osmium", "fileinfo", "-e", osm_pbf], stdout=PIPE, stderr=DEVNULL)
    fileinfo = p.stdout.decode()
    n_objects = {"nodes": 0, "ways": 0, "relations": 0}
    for line in fileinfo.split("\n"):
        for obj in n_objects:
            if f"Number of {obj}" in line:
                n_objects[obj] = int(line.split(":")[-1])
    return n_objects


def _is_empty(osm_pbf):
    """Check if a given .osm.pbf is empty."""
    count = _count_objects(osm_pbf)
    n_objects = sum((n for n in count.values()))
    return not bool(n_objects)


def thematic_extract(osm_pbf, theme, dst_fname):
    """Extract a category of objects from an .osm.pbf file into a GeoPackage.

    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    theme : str
        Category of objects to extract (roads, water, health or ferry).
    dst_fname : str
        Path to output GeoPackage.

    Returns
    -------
    dst_fname : str
        Path to output GeoPackage.

    Raises
    ------
    MissingData
        If the input .osm.pbf file does not contain any feature related to
        the selected theme.
    """
    if theme not in EXTRACTS:
        raise ValueError(
            f"Theme `{theme}` is not supported. Please choose one of the following "
            f"options: {', '.join(EXTRACTS.keys())}."
        )
    expression = EXTRACTS[theme.lower()]["expression"]
    properties = EXTRACTS[theme.lower()]["properties"] + ["geometry"]
    geom_types = EXTRACTS[theme.lower()]["geom_types"]
    log.info(f"Starting thematic extraction of {theme} objects...")

    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        # Filter input .osm.pbf file and export to GeoJSON with osmium-tools
        filtered = tags_filter(
            osm_pbf, os.path.join(tmpdir, "filtered.osm.pbf"), expression
        )

        # Abort if .osm.pbf is empty
        if _is_empty(filtered):
            raise MissingDataError(
                f"No {theme} features in {os.path.basename(osm_pbf)}."
            )

        # An intermediary GeoJSON file so that data can be loaded with GeoPandas
        intermediary = to_geojson(
            filtered, os.path.join(tmpdir, "intermediary.geojson")
        )

        # Drop useless columns
        geodf = gpd.read_file(intermediary)
        log.info(f"Loaded OSM data into a GeoDataFrame with {len(geodf)} records.")
        geodf = _filter_columns(geodf, properties)

        # Convert Polygon or MultiPolygon features to Point
        if theme == "health":
            geodf["geometry"] = geodf.geometry.apply(_centroid)
            log.info("Converted Polygon and MultiPolygon to Point features.")

        # Drop geometries of incorrect types
        geodf = geodf[np.isin(geodf.geom_type, geom_types)]
        log.info(f"Removed objects with invalid geom types ({len(geodf)} remaining).")

        # Reset index, set CRS and save to output file
        geodf = geodf.reset_index(drop=True)
        if not geodf.crs:
            geodf.crs = {"init": "epsg:4326"}
        geodf.to_file(dst_fname, driver="GPKG")
        dst_size = human_readable_size(os.path.getsize(dst_fname))
        log.info(
            f"Saved thematric extract into {os.path.basename(dst_fname)} "
            f"({dst_size})."
        )

    return dst_fname


def create_water_raster(
    osm_water,
    dst_file,
    dst_crs,
    dst_shape,
    dst_transform,
    include_streams=False,
    geom=None,
    overwrite=False,
):
    """Create a raster of surface water from OSM data.

    Parameters
    ----------
    osm_water : str
        Path to input OSM features (.gpkg or .geojson).
    dst_file : str
        Path to output raster.
    dst_crs : CRS
        Target coordinate reference system as a rasterio CRS object.
    dst_shape : tuple of int
        Output raster shape (height, width).
    dst_transform : Affine
        Output raster transform.
    include_streams : bool, optional
        Include smallest rivers and streams.
    overwrite : bool, optional
        Overwrite existing files.
    """
    log.info("Starting rasterization of OSM water objects.")
    if os.path.isfile(dst_file) and not overwrite:
        log.info(f"`{os.path.basename(dst_file)}` already exists. Skipping.")
        return
    if not os.path.isfile(osm_water):
        raise MissingDataError("OSM water data is missing.")

    water = gpd.read_file(osm_water)
    if water.crs != dst_crs:
        water = water.to_crs(dst_crs)
    water_bodies = water[water.water.isin(("lake", "basin", "reservoir", "lagoon"))]
    large_rivers = water[(water.water == "river") | (water.waterway == "riverbank")]
    small_rivers = water[water.waterway.isin(("river", "canal"))]
    streams = water[water.waterway == "stream"]
    features = [water_bodies, large_rivers, small_rivers]
    if include_streams:
        features.append(streams)

    geoms = []
    for objects in features:
        geoms += [g.__geo_interface__ for g in objects.geometry]
    log.info(f"Found {len(geoms)} OSM water objects.")

    rst = rasterize(
        geoms,
        out_shape=dst_shape,
        fill=0,
        default_value=1,
        transform=dst_transform,
        all_touched=True,
        dtype="uint8",
    )

    dst_profile = rasterio.default_gtiff_profile
    dst_profile.update(
        count=1,
        dtype="uint8",
        transform=dst_transform,
        crs=dst_crs,
        height=dst_shape[0],
        width=dst_shape[1],
        nodata=255,
        **default_compression("uint8"),
    )

    with rasterio.open(dst_file, "w", **dst_profile) as dst:
        dst.write(rst, 1)
        log.info(f"OSM water raster saved as `{os.path.basename(dst_file)}`.")
