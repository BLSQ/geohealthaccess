"""Quality checks for downloaded files, input and output data."""

import os
import subprocess
from tempfile import TemporaryDirectory
import zipfile

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom

from geohealthaccess import storage
from geohealthaccess.errors import MissingDataError, BadDataError


def srtm(data_dir):
    """Check quality of downloaded SRTM tiles.

    Parameters
    ----------
    data_dir : str
        Directory where SRTM tiles are stored.

    Raises
    ------
    MissingDataError
        If no elevation tile is found.
    BadDataError
        If metadata is different than expected for any of the tile.
    """
    tiles = [
        os.path.join(data_dir, f)
        for f in storage.ls(data_dir)
        if f.endswith(".hgt.zip")
    ]

    # At least one tile should be downloaded
    try:
        assert len(tiles) > 0
    except AssertionError:
        raise MissingDataError("Elevation tiles not found.")

    for tile in tiles:
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            tile_tmp = os.path.join(tmp_dir, os.path.basename(tile))
            with zipfile.ZipFile(tile_tmp, "r") as archive:
                img = archive.namelist()[0]
                archive.extractall(tmp_dir)
            with rasterio.open(os.path.join(tmp_dir, img)) as src:
                try:
                    assert src.driver == "SRTMHGT"
                    assert src.dtypes[0] == "int16"
                    assert src.crs == CRS.from_epsg(4326)
                    assert src.width == 3601
                    assert src.height == 3601
                    assert src.nodata == -32768
                except AssertionError:
                    raise BadDataError(
                        f"Incorrect metadata for elevation tile {tile.split(os.sep)[-1]}."
                    )


def cglc(data_dir):
    """Quality check of downloaded land cover data.

    Parameters
    ----------
    data_dir : str
        Directory where input land cover files are stored.

    Raises
    ------
    MissingDataError
        If no land cover tile is found.
    BadDataError
        If classes are missing in the tile archive, or if metadata is
        different than expected.
    """
    tiles = [
        os.path.join(data_dir, f) for f in storage.ls(data_dir) if f.endswith(".zip")
    ]
    try:
        assert len(tiles) > 0
    except AssertionError:
        raise MissingDataError("Land cover tiles not found.")

    for tile in tiles:
        rasters = [
            f for f in zipfile.ZipFile(tile, "r").namelist() if f.endswith(".tif")
        ]
        try:
            assert len(rasters) == 20
        except AssertionError:
            raise BadDataError(
                f"Missing raster in CGLC tile archive {tile.split(os.sep)[-1]}."
            )
        for raster in rasters:
            raster_path = f"zip://{tile}!/{raster}"
            try:
                with rasterio.open(raster_path) as src:
                    assert src.crs == CRS.from_epsg(4326)
                    assert src.dtypes[0] == "uint8"
                    assert src.nodata == 255
            except AssertionError:
                raise BadDataError(
                    f"Incorrect metadata for CGLC tile {tile.split(os.sep)[-1]}."
                )


def osm(data_dir):
    """Quality check of downloaded OSM data.

    Parameters
    ----------
    data_dir : str
        Directory where input OSM file is stored.

    Raises
    ------
    MissingDataError
        If no OSM data file is found.
    BadDataError
        If latest OSM data file have null size or null bounds.
    """
    osm_files = [f for f in os.listdir(data_dir) if f.endswith(".osm.pbf")]
    try:
        assert len(osm_files) > 0
    except AssertionError:
        raise MissingDataError("OSM data file not found.")

    # Find latest OSM file if several are available
    if len(osm_files) == 1:
        latest = osm_files[0]
    else:
        latest, date = None, 0
        for fname in osm_files:
            basename = fname.split(".")[0]
            date_str = basename.split("-")[-1]
            if int(date_str) > date:
                date = int(date_str)
                latest = fname
    try:
        assert latest
    except AssertionError:
        raise MissingDataError("Unable to find latest OSM data file.")

    p = subprocess.run(
        ["osmium", "fileinfo", os.path.join(data_dir, latest)],
        stdout=subprocess.PIPE,
        check=True,
    )
    fileinfo = p.stdout.decode("UTF-8").split("\n")
    fileinfo = [line.strip() for line in fileinfo if line]

    # Size not null
    size_i = [line.startswith("Size:") for line in fileinfo].index(True)
    size = int(fileinfo[size_i].split(":")[-1])
    try:
        assert size
    except AssertionError:
        raise BadDataError(f"OSM file {latest} is not valid (null size).")

    # BBOX not null
    bbox_i = [line.startswith("Bounding boxes:") for line in fileinfo].index(True) + 1
    bbox_str = fileinfo[bbox_i].replace("(", "").replace(")", "")
    for coord in bbox_str.split(","):
        try:
            assert float(coord)
        except (AssertionError, ValueError):
            raise BadDataError(f"OSM file {latest} is not valid (null bounds).")


def worldpop(data_dir):
    """Quality check of downloaded worldpop data.

    Parameters
    ----------
    data_dir : str
        Directory where worldpop raster is stored.

    Raises
    ------
    MissingDataError
        If no worldpop raster is found.
    BadDataError
        If raster metadata is different than expected.
    """
    data_dir = "Data/Input/Population"
    try:
        pop_file = [
            f for f in os.listdir(data_dir) if f.endswith(".tif") and "ppp" in f
        ][0]
    except IndexError:
        raise MissingDataError("Worldpop raster not found.")
    pop_file = os.path.join(data_dir, pop_file)

    try:
        with rasterio.open(pop_file) as src:
            assert src.dtypes[0] == "float32"
            assert src.nodata == -99999
            assert src.crs == CRS.from_epsg(4326)
    except AssertionError:
        raise BadDataError(
            f"Incorrect metadata in population raster {pop_file.split(os.sep)[-1]}."
        )


def _nan_ratio(dataset, aoi, band=1):
    """Ratio of NaN pixels in a given AOI.

    Parameters
    ----------
    dataset : raster
        Raster dataset as returned by rasterio.open().
    aoi : Polygon
        Area of interest as a shapely polygon.
    band : int, optional
        Band to process (starting from 1).

    Returns
    -------
    ratio : float
        Ratio of NaN values.
    """
    aoi = transform_geom(CRS.from_epsg(4326), dataset.crs, aoi.__geo_interface__)
    mask = rasterize(
        [aoi], out_shape=dataset.shape, transform=dataset.transform, dtype="uint8"
    )
    total = np.count_nonzero(mask)
    n_nan = np.count_nonzero(dataset.read(band)[mask == 1] == dataset.nodata)
    return n_nan / total


def _zero_ratio(dataset, aoi, band=1):
    """Ratio of zero values in a given AOI.

    Parameters
    ----------
    dataset : raster
        Raster dataset as returned by rasterio.open().
    aoi : Polygon
        Area of interest as a shapely polygon.
    band : int, optional
        Band to process (starting from 1).

    Returns
    -------
    ratio : float
        Ratio of zero values.
    """
    aoi = transform_geom(CRS.from_epsg(4326), dataset.crs, aoi.__geo_interface__)
    mask = rasterize(
        [aoi], out_shape=dataset.shape, transform=dataset.transform, dtype="uint8"
    )
    total = np.count_nonzero(mask)
    n_zero = np.count_nonzero(dataset.read(band)[mask == 1] == 0)
    return n_zero / total


def grid(data_dir):
    """Check that processed rasters are all aligned on a common grid.

    Parameters
    ----------
    data_dir : str
        Directory where preprocessed rasters are stored.

    Raises
    ------
    BadDataError
        If shapes, CRS or transforms varie among rasters.
    """
    shapes, transforms, crs = [], [], []
    rasters = [
        os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".tif")
    ]
    for raster in rasters:
        with rasterio.open(raster) as src:
            shapes.append(src.shape)
            transforms.append(src.transform)
            crs.append(src.crs)
    try:
        assert len(set(shapes)) == 1
    except AssertionError:
        raise BadDataError("Input rasters are not aligned (shapes differ).")
    try:
        assert len(set(transforms)) == 1
    except AssertionError:
        raise BadDataError("Input rasters are not aligned (transforms differ).")
    try:
        assert len(set(crs)) == 1
    except AssertionError:
        raise BadDataError("Input rasters are not aligned (CRS differ).")


def elevation(data_dir, aoi):
    """Quality check for preprocessed elevation raster.

    Parameters
    ----------
    data_dir : str
        Directory where preprocessed elevation raster is stored.
    aoi : Polygon
        Area of interest as a shapely geometry.

    Raises
    ------
    MissingDataError
        If preprocessed elevation raster is not found.
    BadDataError
        If raster metadata is different than expected.
    """
    if not os.path.isfile(os.path.join(data_dir, "elevation.tif")):
        raise MissingDataError("Preprocessed elevation raster not found.")
    with rasterio.open(os.path.join(data_dir, "elevation.tif")) as src:
        try:
            assert src.crs
            assert src.nodata == -32768
            assert src.dtypes[0] == "int16"
            assert _nan_ratio(src, aoi) < 0.1
            assert src.read(1).max() < 9000
        except AssertionError:
            raise BadDataError("Incorrect metadata in preprocessed elevation raster.")


def land_cover(data_dir, aoi):
    """Quality check for preprocessed land cover raster.

    Parameters
    ----------
    data_dir : str
        Directory where preprocessed land cover raster is stored.
    aoi : Polygon
        Area of interest as a shapely geometry.

    Raises
    ------
    MissingDataError
        If preprocessed land cover raster is not found.
    BadDataError
        If raster metadata is different than expected or if invalid values
        are detected (too many NaN, negative values).
    """
    if not os.path.isfile(os.path.join(data_dir, "land_cover.tif")):
        raise MissingDataError("Preprocessed land cover raster not found.")
    with rasterio.open(os.path.join(data_dir, "land_cover.tif")) as src:
        try:
            assert src.dtypes[0] == "uint8"
            assert src.nodata == 255
            assert src.count == 9
            assert src.crs
        except AssertionError:
            raise BadDataError("Incorrect metadata in preprocessed land cover raster.")
        for band in range(1, 10):
            try:
                assert _nan_ratio(src, aoi, band) < 0.1
            except AssertionError:
                raise BadDataError(
                    f"Invalid values in land cover raster. Too many NaN in band {band}."
                )
            try:
                assert src.read(band).min() >= 0
            except AssertionError:
                raise BadDataError(
                    f"Invalid values in land cover raster. Negative values in band {band}."
                )


def roads(data_dir, aoi):
    """Quality check for roads geopackage.

    Parameters
    ----------
    data_dir : str
        Directory where roads.gpkg is stored.
    aoi : Polygon
        Area of interest as a shapely geometry.

    Raises
    ------
    MissingDataError
        If roads.gpkg is not found.
    BadDataError
        If no CRS is assigned, if no feature is detected inside the AOI,
        or if geometries are invalid.
    """
    if not os.path.isfile(os.path.join(data_dir, "roads.gpkg")):
        raise MissingDataError("roads.gpkg not found.")
    roads = gpd.read_file(os.path.join(data_dir, "roads.gpkg"))
    try:
        assert roads.crs
    except AssertionError:
        raise BadDataError("roads.gpkg: no CRS assigned.")
    try:
        assert not roads[roads.intersects(aoi)].empty
    except AssertionError:
        raise BadDataError("roads.gpkg: no feature detected in AOI.")
    try:
        assert roads.is_valid.all()
    except AssertionError:
        raise BadDataError("roads.gpkg: invalid feature(s) detected.")
    for highway in ("primary", "secondary", "tertiary"):
        try:
            assert not roads[roads.highway == highway].empty
        except AssertionError:
            raise BadDataError(f"roads.gpkg: no {highway} roads detected.")


def water(data_dir, aoi):
    """Quality check for preprocessed water raster.

    Parameters
    ----------
    data_dir : str
        Directory where water_osm.tif is stored.
    aoi : Polygon
        Area of interest as a shapely geometry.

    Raises
    ------
    MissingDataError
        If water_osm.tif is not found.
    BadDataError
        If raster metadata is different than expected or if invalid values are
        detected.
    """
    if not os.path.isfile(os.path.join(data_dir, "water_osm.tif")):
        raise MissingDataError("Preprocessed water raster not found.")
    with rasterio.open(os.path.join(data_dir, "water_osm.tif")) as src:
        try:
            assert src.crs
            assert src.nodata == 255
            assert src.dtypes[0] == "uint8"
        except AssertionError:
            raise BadDataError("Incorrect metadata in preprocessed water raster.")
        try:
            assert _nan_ratio(src, aoi) < 0.1
        except AssertionError:
            raise BadDataError("Invalid values in water raster: too many NaN.")
        try:
            assert np.count_nonzero((src.read() > 0) & (src.read() != 255))
        except AssertionError:
            raise BadDataError("Invalid values in water raster: no positive values.")


def cost(data_dir, aoi):
    """Quality check for computed travel times.

    Parameters
    ----------
    data_dir : str
        Directory where cost rasters are stored.
    aoi : Polygon
        Area of interest as a shapely geometry.

    Raises
    ------
    MissingDataError
        If no cost raster is found.
    BadDataError
        If raster metadata is different than expected or if invalid values are
        detected.
    """
    cost_rasters = [
        f for f in os.listdir(data_dir) if f.startswith("cost_") and f.endswith(".tif")
    ]
    try:
        assert len(cost_rasters)
    except AssertionError:
        raise MissingDataError("Cost raster not found.")
    for raster in cost_rasters:
        with rasterio.open(os.path.join(data_dir, raster)) as src:
            try:
                assert src.crs
                assert src.dtypes[0] == "float64"
                assert src.nodata == -9999
            except AssertionError:
                raise BadDataError(f"Incorrect metadata for cost raster {raster}.")
            try:
                assert _nan_ratio(src, aoi) < 0.25
            except AssertionError:
                raise BadDataError(f"Too many NaN values in cost raster {raster}.")
            try:
                assert src.read(masked=True).mean() > 0
            except AssertionError:
                raise BadDataError(f"Invalid values detected in cost raster {raster}.")
