"""Main application."""

import json
import os
import shutil
import sys

import geopandas as gpd
import numpy as np
import subprocess
import rasterio
from appdirs import user_cache_dir
from shapely import wkt
from loguru import logger
import pandas as pd
from tempfile import TemporaryDirectory
from rasterstats import zonal_stats
from pkg_resources import resource_filename
from rasterio.crs import CRS

from geohealthaccess import (
    cglc,
    grasshelper,
    gsw,
    osm,
    srtm,
    storage,
    worldpop,
)
from geohealthaccess import preprocessing
from geohealthaccess.errors import GeoHealthAccessError
from geohealthaccess.preprocessing import create_grid
from geohealthaccess.utils import country_geometry, random_string


class GeoHealthAccess:
    def __init__(
        self,
        raw_dir,
        input_dir,
        output_dir,
        country,
        crs="EPSG:3857",
        resolution=100,
        area_of_interest=None,
        logs_dir=None,
        log_level="DEBUG",
    ):
        self.raw_dir = None
        self.input_dir = None
        self.output_dir = None
        self.logs_dir = None
        if raw_dir:
            self.raw_dir = raw_dir.strip()
        if input_dir:
            self.input_dir = input_dir.strip()
        if output_dir:
            self.output_dir = output_dir.strip()
        if logs_dir:
            self.logs_dir = logs_dir.strip()

        self.log_level = log_level

        if len(country) == 3:
            self.country = country
        else:
            raise GeoHealthAccessError(f"{country} is not a ISO A3 country code.")

        for dir_ in (self.raw_dir, self.input_dir, self.output_dir, self.logs_dir):
            if dir_:
                location = storage.Location(dir_)
                if location.protocol not in ("local", "s3", "gcs"):
                    raise GeoHealthAccessError(f"{dir_} is not a supported directory.")

        if not isinstance(resolution, int) or resolution < 50 or resolution > 1000:
            raise GeoHealthAccessError(
                "Resolution should be an integer between 50 and 1000."
            )

        if area_of_interest:
            self.area_of_interest = area_of_interest
        else:
            self.area_of_interest = country_geometry(country)

        if isinstance(crs, str):
            self.crs = rasterio.crs.CRS.from_string(crs)
        elif isinstance(crs, rasterio.crs.CRS):
            self.crs = crs
        else:
            raise GeoHealthAccess("CRS must be a CRS object or a string.")

        self.resolution = resolution
        self.transform, self.shape, self.bounds = create_grid(
            self.area_of_interest, self.crs, self.resolution
        )

        self.moving_speeds = self.load_moving_speeds()
        self.mask = self.compute_mask()
        self.setup_logging()
        self.setup_cache()
        self.create_dirs()

    def setup_logging(self):
        logger.remove()
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
                "<level>{level}</level> <cyan>{name}</cyan>:<cyan>{function}"
                "</cyan>:<cyan>{line}</cyan> {message}"
            ),
            enqueue=True,
            backtrace=True,
            level=self.log_level,
        )
        logger.enable("")

    def _cached_dir(self, dir_):
        """Get path to the local cache version of a remote directory.

        If dir_ is a local directory, None is returned.

        Parameters
        ----------
        dir_ : str
            URL to a remote directory (starting with s3:// or gcs://).
        """
        if not storage.is_local(dir_):
            return os.path.join(self.cache_dir, os.path.basename(dir_))
        else:
            return None

    def setup_cache(self):
        """Replace cloud data directories with local cache directories.

        All IO operations will use the cache directories and be synced with
        the remote directories on-demand.
        """
        cache_id = random_string(length=16)
        self.cache_dir = os.path.join(user_cache_dir("geohealthaccess"), cache_id)

        self.raw_dir_remote = None
        self.input_dir_remote = None
        self.output_dir_remote = None
        self.logs_dir_remote = None

        if self.raw_dir:
            if not storage.is_local(self.raw_dir):
                self.raw_dir_remote = self.raw_dir
                self.raw_dir = self._cached_dir(self.raw_dir)

        if self.input_dir:
            if not storage.is_local(self.input_dir):
                self.input_dir_remote = self.input_dir
                self.input_dir = self._cached_dir(self.input_dir)

        if self.output_dir:
            if not storage.is_local(self.output_dir):
                self.output_dir_remote = self.output_dir
                self.output_dir = self._cached_dir(self.output_dir)

        if self.logs_dir:
            if not storage.is_local(self.logs_dir):
                self.logs_dir_remote = self.logs_dir
                self.logs_dir = self._cached_dir(self.logs_dir)

    def create_dirs(self):
        """Create data and logs directories."""
        for dir_ in (
            self.raw_dir,
            self.input_dir,
            self.output_dir,
            self.logs_dir,
        ):
            if dir_:
                storage.mkdir(dir_)

    def cache(self, show_progress=True, overwrite=False):
        """Cache remote data directories."""
        remote_dirs = [
            self.raw_dir_remote,
            self.input_dir_remote,
            self.output_dir_remote,
            self.logs_dir_remote,
        ]
        local_dirs = [
            self.raw_dir,
            self.input_dir,
            self.output_dir,
            self.logs_dir,
        ]
        for remote_dir, local_dir in zip(remote_dirs, local_dirs):
            if remote_dir:
                storage.recursive_download(
                    remote_dir,
                    local_dir,
                    show_progress=show_progress,
                    overwrite=overwrite,
                )

    def upload(self, show_progress=True, overwrite=False):
        """Upload cached data to remote data directories."""
        remote_dirs = [
            self.raw_dir_remote,
            self.input_dir_remote,
            self.output_dir_remote,
            self.logs_dir_remote,
        ]
        local_dirs = [
            self.raw_dir,
            self.input_dir,
            self.output_dir,
            self.logs_dir,
        ]
        for remote_dir, local_dir in zip(remote_dirs, local_dirs):
            if remote_dir:
                storage.recursive_upload(
                    local_dir,
                    remote_dir,
                    show_progress=show_progress,
                    overwrite=overwrite,
                )

    def dump_spatial_info(self):
        """Dump spatial information into a JSON file."""
        meta = {
            "country": self.country,
            "transform": self.transform.to_gdal(),
            "crs": self.crs.to_string(),
            "shape": self.shape,
            "area": self.area_of_interest.wkt,
            "bounds": self.bounds,
            "resolution": self.resolution,
        }
        with open(os.path.join(self.input_dir, "meta.json"), "w") as dst:
            json.dump(meta, dst)

    def update_spatial_info(self):
        """Update spatial information from a JSON file."""
        with open(os.path.join(self.input_dir, "meta.json")) as f:
            meta = json.load(f)
        self.transform = rasterio.Affine.from_gdal(*meta["transform"])
        self.resolution = int(meta["resolution"])
        self.crs = rasterio.crs.CRS.from_string(meta["crs"])
        self.shape = tuple(meta["shape"])
        self.area_of_interest = wkt.loads(meta["area"])
        self.bounds = tuple(meta["bounds"])
        self.mask = self.compute_mask()

    def load_moving_speeds(self, fp=None):
        """Load moving speeds from a JSON file.

        Parameters
        ----------
        fp : str, optional
            Path to moving speeds JSON file. Can be an s3:// or gcs:// URL.

        Returns
        -------
        dict
            Road and land cover moving speeds.
        """
        if fp:
            with storage.open_(fp) as f:
                return json.load(f)
        else:
            with open(resource_filename(__name__, "resources/moving-speeds.json")) as f:
                return json.load(f)

    def download(
        self,
        earthdata_username=None,
        earthdata_password=None,
        show_progress=True,
        overwrite=False,
    ):
        """Download raw data.

        Download required datasets from Copernicus Global Land Cover,
        OpenStreetMap, Global Surface Water Project, SRTM and WorldPop.

        Parameters
        ----------
        earthdata_username : str, optional
            NASA EarthData username. Can also be provided as an environment
            variable.
        earthdata_password : str, optional
            NASA EarthData password. Can also be provided as an environment
            variable.
        show_progress : bool, optional
            Show progress bar.
        overwrite : bool, optional
            Overwrite existing files.
        """
        # Population counts
        worldpop.download(
            self.country,
            os.path.join(self.raw_dir, "worldpop"),
            un_adj=True,
            show_progress=show_progress,
            overwrite=overwrite,
        )

        # Land cover
        catalog = cglc.CGLC()
        catalog.download_all(
            self.area_of_interest,
            os.path.join(self.raw_dir, "cglc"),
            overwrite=overwrite,
        )

        # OpenStreetMap
        geofabrik = osm.Geofabrik()
        geofabrik.download(
            self.country,
            os.path.join(self.raw_dir, "osm"),
            show_progress=show_progress,
            overwrite=overwrite,
        )

        # Surface water
        catalog = gsw.GSW()
        tiles = catalog.search(self.area_of_interest)
        for tile in tiles:
            catalog.download(
                tile,
                "seasonality",
                os.path.join(self.raw_dir, "gsw"),
                show_progress=show_progress,
                overwrite=overwrite,
            )

        # Elevation
        catalog = srtm.SRTM()
        if not earthdata_username and not earthdata_password:
            earthdata_username = os.getenv("EARTHDATA_USERNAME")
            earthdata_password = os.getenv("EARTHDATA_PASSWORD")
        if not earthdata_username or not earthdata_password:
            raise GeoHealthAccessError("NASA EarthData credentials not provided.")
        catalog.authentify(earthdata_username, earthdata_password)
        tiles = catalog.search(self.area_of_interest)
        for tile in tiles:
            catalog.download(
                tile,
                os.path.join(self.raw_dir, "srtm"),
                show_progress=show_progress,
                overwrite=overwrite,
            )

    def preprocessing(self, show_progress=True, overwrite=False):
        """Preprocess input data to a common raster grid.

        Parameters
        ----------
        show_progress : bool, optional
            Show progress bars.
        overwrite : bool, optional
            Overwrite existing files.
        """

        # land cover
        cglc.preprocess(
            src_dir=os.path.join(self.raw_dir, "cglc"),
            dst_dir=self.input_dir,
            geom=self.area_of_interest,
            crs=self.crs,
            res=self.resolution,
            overwrite=overwrite,
        )

        # topography
        srtm.preprocess(
            src_dir=os.path.join(self.raw_dir, "srtm"),
            dst_elev=os.path.join(self.input_dir, "elevation.tif"),
            dst_slope=os.path.join(self.input_dir, "slope.tif"),
            dst_crs=self.crs,
            dst_res=self.resolution,
            geom=self.area_of_interest,
            overwrite=overwrite,
        )

        # openstreetmap
        osm.extract_osm_objects(
            src_file=storage.glob(os.path.join(self.raw_dir, "osm", "*.osm.pbf"))[0],
            dst_dir=self.input_dir,
            overwrite=overwrite,
        )
        osm.create_water_raster(
            src_file=os.path.join(self.input_dir, "water.gpkg"),
            dst_file=os.path.join(self.input_dir, "water_osm.tif"),
            dst_crs=self.crs,
            dst_shape=self.shape,
            dst_transform=self.transform,
            include_streams=False,
            overwrite=overwrite,
        )

        # global surface water
        gsw.preprocess(
            src_dir=os.path.join(self.raw_dir, "gsw"),
            dst_file=os.path.join(self.input_dir, "water_gsw.tif"),
            dst_crs=self.crs,
            dst_res=self.resolution,
            geom=self.area_of_interest,
            overwrite=overwrite,
        )

        # copy worldpop data without preprocessing
        src = storage.glob(os.path.join(self.raw_dir, "worldpop", "*ppp*.tif"))[0]
        dst = os.path.join(self.input_dir, "population.tif")
        if overwrite or not os.path.isfile(dst):
            shutil.copyfile(src, dst)

    def compute_mask(self):
        """Raster binary mask from area of interest.

        Returns
        -------
        2d array
            Area of interest as a binary raster mask (False=Outside boundaries.)
        """
        geom = rasterio.warp.transform_geom(
            src_crs=CRS.from_epsg(4326),
            dst_crs=self.crs,
            geom=self.area_of_interest.__geo_interface__,
        )
        raster = rasterio.features.rasterize(
            shapes=[geom],
            fill=0,
            default_value=1,
            out_shape=self.shape,
            all_touched=True,
            transform=self.transform,
            dtype="uint8",
        )
        return raster.astype(np.bool_)

    @property
    def profile(self):
        """Default raster profile."""
        return rasterio.profiles.DefaultGTiffProfile(
            count=1,
            height=self.shape[0],
            width=self.shape[1],
            transform=self.transform,
            crs=self.crs,
            compress="zstd",
            predictor=3,
            dtype="float32",
            nodata=-1,
        )

    def moving_obstacle(self, max_slope=35):
        """Compute a boolean raster of obstacles to travel.

        Pixels with water or high slopes are marked as impassable.
        NB: On-roads moving speeds will have the priority over this.

        Parameters
        ----------
        max_slope : int, optional
            Max. passable slope in degrees.

        Returns
        -------
        2d array
            Output mask (True pixels are impassable, False are passable).
        """
        logger.info(f"Computing obstacle raster (max slope = {max_slope} degrees).")
        obstacle = np.zeros(shape=self.shape, dtype=np.bool_)
        with rasterio.open(os.path.join(self.input_dir, "water_osm.tif")) as src:
            obstacle[src.read(1, masked=True) >= 1] = True
        with rasterio.open(os.path.join(self.input_dir, "water_gsw.tif")) as src:
            obstacle[src.read(1, masked=True) >= 10] = True
        with rasterio.open(os.path.join(self.input_dir, "slope.tif")) as src:
            obstacle[src.read(1, masked=True) >= max_slope] = True
        return obstacle

    def off_road_speed(self):
        """Compute off-road moving speeds in km/h based on land cover.

        Returns
        -------
        2d array
            Off-road speed (in km/h) as a 2d numpy array.
        """
        logger.info("Calculating off-road speed.")
        speed = np.zeros(shape=self.shape, dtype=np.float32)
        rasters = storage.glob(os.path.join(self.input_dir, "landcover_*.tif"))
        for raster in rasters:
            label = os.path.basename(raster).replace(".tif", "").split("_")[-1]
            with rasterio.open(raster) as src:
                cover = src.read(1, masked=True)
                speed += (cover / 100.0) * self.moving_speeds["land-cover"][label]
        speed[speed < 0] = np.nan
        return speed

    def segment_speed(self, highway, tracktype=None, smoothness=None, surface=None):
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

        Returns
        -------
        float
            Speed in km/h.
        """
        # Ignore unsupported road segments
        if highway not in self.moving_speeds["transport"]["highway"]:
            return None

        # Get base speed and adjust depending on road quality
        base_speed = self.moving_speeds["transport"]["highway"][highway]
        tracktype = self.moving_speeds["transport"]["tracktype"].get(tracktype, 1)
        smoothness = self.moving_speeds["transport"]["smoothness"].get(smoothness, 1)
        surface = self.moving_speeds["transport"]["surface"].get(surface, 1)
        return base_speed * min(tracktype, smoothness, surface)

    def on_road_speed(self, mode="car"):
        """Compute on-road moving speeds in km/h based on transport network.

        Parameters
        ----------
        mode : str, optional
            Transport mode: `car`, `walk` or `bike`.

        Returns
        -------
        2d array
            On-road speed (in km/h) as a 2d numpy array.
        """
        # Load network data (roads, tracks, paths)
        roads = gpd.read_file(os.path.join(self.input_dir, "roads.gpkg"))
        roads = roads.to_crs(self.crs)

        logger.info(f"Calculating on-road speeds ({len(roads)} road segments).")

        # Build a list of features with geometries and associated speed
        features = []
        for _, row in roads.iterrows():
            # Road segments
            segment_speed = self.segment_speed(
                row.highway,
                row.tracktype,
                row.smoothness,
                row.surface,
            )
            if segment_speed:
                features.append((row.geometry.__geo_interface__, segment_speed))
        if os.path.isfile(os.path.join(self.input_dir, "ferry.gpkg")):
            # Add ferry features
            ferry = gpd.read_file(os.path.join(self.input_dir, "ferry.gpkg"))
            ferry = ferry.to_crs(self.crs)
            segment_speed = self.moving_speeds["transport"]["route"]["ferry"]
            features += [
                (geom.__geo_interface__, segment_speed) for geom in ferry.geometry
            ]

        raster = rasterio.features.rasterize(
            shapes=features,
            out_shape=self.shape,
            transform=self.transform,
            fill=0,
            all_touched=True,
            dtype="float32",
        )
        raster[~self.mask] = np.nan
        return raster

    def friction_surface(self, mode="car", max_slope=35, walk_speed=5):
        """Compute a friction surface.

        Friction is computed from land cover, transport network, topography and
        surface water.

        Parameters
        ----------
        mode : str, optional
            Transport mode: "car", "walk" or "bike".
        max_slope : int, optional
            Max. passable slope in degrees.
        walk_speed : float, optional
            Walking speed on roads.

        Returns
        -------
        2d array
            Friction surface as a 2d numpy array.
        """
        logger.info(f"Computing friction surface ({mode} scenario).")
        off_road = self.off_road_speed() / 3.6  # speed in m/s
        on_road = self.on_road_speed(mode=mode) / 3.6  # speed in m/s
        obstacle = self.moving_obstacle(max_slope=max_slope)
        friction = np.zeros(shape=self.shape, dtype=np.float64)
        off_road[obstacle] = 0
        speed = np.maximum(off_road, on_road)
        if mode == "walk":
            speed[speed > walk_speed] = walk_speed
            # when using r.walk, compute time to cross one meter
            friction[speed != 0] = 1 / speed[speed != 0]
        else:
            # when using r.cost, compute time to cross one pixel
            friction[speed != 0] = self.transform.a / speed[speed != 0]
        friction[speed == 0] = np.nan
        friction[np.isnan(friction)] = np.nan
        friction[np.isinf(friction)] = np.nan
        friction[~self.mask] = np.nan

        dst_file = os.path.join(self.output_dir, f"friction_{mode}.tif")
        dst_profile = self.profile
        dst_profile["dtype"] = "float64"
        with rasterio.open(dst_file, "w", **dst_profile) as dst:
            dst.write(friction, 1)
        return friction

    def health_facilities(self):
        """Get health facilities from OpenStreetMap.

        Returns
        -------
        GeoDataFrame
            OSM health facilities as points.
        """
        health = gpd.read_file(os.path.join(self.input_dir, "health.gpkg"))
        return health.to_crs(self.crs)

    def isotropic_costdistance(
        self, src_friction, src_target, dst_dir, max_memory=8000
    ):
        """Isotropic cost distance analysis."""
        logger.info("Starting isotropic cost-distance modeling.")
        grass_datadir = os.path.join(self.cache_dir, f"GRASSDATA_{random_string()}")
        if os.path.isdir(grass_datadir):
            shutil.rmtree(grass_datadir)
        os.makedirs(grass_datadir)
        dst_dir = os.path.abspath(dst_dir)
        os.makedirs(dst_dir, exist_ok=True)

        # Write friction raster to disk as required by GRASS
        profile = self.profile.copy()
        profile.update(dtype="float64", nodata=-1, compress=None, predictor=None)
        src_friction_fp = os.path.join(grass_datadir, "friction.tif")
        with rasterio.open(src_friction_fp, "w", **profile) as dst:
            dst.write(src_friction, 1)

        # Write health facilities to disk as required by GRASS
        if src_target.crs != self.crs:
            src_target = src_target.to_crs(self.crs)
        src_target_fp = os.path.join(grass_datadir, "target.gpkg")
        src_target.to_file(src_target_fp, driver="GPKG")

        logger.info("Setting up GRASS GIS environment.")
        grasshelper.setup_environment(grass_datadir, self.crs)
        logger.info(f"Loading {os.path.basename(src_friction_fp)}.")
        grasshelper.grass_execute(
            "r.in.gdal", input=src_friction_fp, output="friction", overwrite=True
        )
        grasshelper.grass_execute("g.region", raster="friction")
        logger.info(f"Loading {os.path.basename(src_target_fp)}.")
        grasshelper.grass_execute("v.in.ogr", input=src_target_fp, output="target")
        logger.info("Calculating costs.")
        grasshelper.grass_execute(
            "r.cost",
            flags="kn",
            input="friction",
            output="cost",
            nearest="nearest",
            outdir="backlink",
            start_points="target",
            memory=max_memory,
        )
        logger.info("Writing output rasters to disk.")
        grasshelper.grass_execute(
            "r.out.gdal",
            input="cost",
            output=os.path.join(dst_dir, "cost.tif"),
            format="GTiff",
            nodata=-1,
            overwrite=True,
        )
        grasshelper.grass_execute(
            "r.out.gdal",
            input="backlink",
            output=os.path.join(dst_dir, "backlink.tif"),
            format="GTiff",
            nodata=-1,
            overwrite=True,
        )
        grasshelper.grass_execute(
            "r.out.gdal",
            input="nearest",
            output=os.path.join(dst_dir, "nearest.tif"),
            format="GTiff",
            overwrite=True,
        )
        shutil.rmtree(grass_datadir)

    def anisotropic_costdistance(
        self, src_friction, src_target, dst_dir, max_memory=8000
    ):
        """Anisotropic cost distance analysis."""
        logger.info("Starting anisotropic cost-distance modeling.")
        grass_datadir = os.path.join(self.cache_dir, f"GRASSDATA_{random_string()}")
        if os.path.isdir(grass_datadir):
            shutil.rmtree(grass_datadir)
        os.makedirs(grass_datadir)
        dst_dir = os.path.abspath(dst_dir)
        os.makedirs(dst_dir, exist_ok=True)

        # Write friction raster to disk as required by GRASS
        profile = self.profile.copy()
        profile.update(dtype="float64", nodata=-1, compress=None, predictor=None)
        src_friction_fp = os.path.join(grass_datadir, "friction.tif")
        with rasterio.open(src_friction_fp, "w", **profile) as dst:
            dst.write(src_friction, 1)

        # Write health facilities to disk as required by GRASS
        if src_target.crs != self.crs:
            src_target = src_target.to_crs(self.crs)
        src_target_fp = os.path.join(grass_datadir, "target.gpkg")
        src_target.to_file(src_target_fp, driver="GPKG")

        logger.info("Setting up GRASS GIS environment.")
        grasshelper.setup_environment(grass_datadir, self.crs)
        logger.info(f"Loading {os.path.basename(src_friction_fp)}.")
        grasshelper.grass_execute(
            "r.in.gdal", input=src_friction_fp, output="friction", overwrite=True
        )
        grasshelper.grass_execute("g.region", raster="friction")
        logger.info("Loading elevation.tif.")
        grasshelper.grass_execute(
            "r.in.gdal",
            input=os.path.join(self.input_dir, "elevation.tif"),
            output="elevation",
        )
        logger.info(f"Loading {os.path.basename(src_target_fp)}.")
        grasshelper.grass_execute("v.in.ogr", input=src_target_fp, output="target")
        logger.info("Calculating costs.")
        grasshelper.grass_execute(
            "r.walk",
            flags="kn",
            friction="friction",
            elevation="elevation",
            output="cost",
            nearest="nearest",
            outdir="backlink",
            start_points="target",
            memory=max_memory,
        )
        logger.info("Writing output rasters to disk.")
        grasshelper.grass_execute(
            "r.out.gdal",
            input="cost",
            output=os.path.join(dst_dir, "cost.tif"),
            format="GTiff",
            nodata=-1,
            overwrite=True,
        )
        grasshelper.grass_execute(
            "r.out.gdal",
            input="backlink",
            output=os.path.join(dst_dir, "backlink.tif"),
            format="GTiff",
            nodata=-1,
            overwrite=True,
        )
        grasshelper.grass_execute(
            "r.out.gdal",
            input="nearest",
            output=os.path.join(dst_dir, "nearest.tif"),
            format="GTiff",
            overwrite=True,
        )
        shutil.rmtree(grass_datadir)

    def fill(self, src_array, nodata=-1):
        """Fill nodata pixels with interpolated values.

        Parameters
        ----------
        src_array : 2d array
            Input raster as a numpy 2d array.

        Returns
        -------
        2d array
            Output raster.
        """
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            profile = self.profile
            profile.update(dtype=src_array.dtype, nodata=nodata)
            src_raster = os.path.join(tmp_dir, "src_raster.tif")
            dst_raster = os.path.join(tmp_dir, "dst_raster.tif")
            with rasterio.open(src_raster, "w", **profile) as dst:
                dst.write(src_array, 1)
            subprocess.run(
                [
                    "gdal_fillnodata.py",
                    "-md",
                    "1000",
                    "-si",
                    "0",
                    src_raster,
                    "-of",
                    "GTiff",
                    dst_raster,
                ],
                capture_output=True,
            )
            preprocessing.mask_raster(dst_raster, self.area_of_interest)
            with rasterio.open(dst_raster) as src:
                dst_array = src.read(1)
        return dst_array

    def population_counts(self, areas):
        """Count population in each area.

        Based on the WorldPop dataset.

        Parameters
        ----------
        areas : GeoDataFrame
            Input shapes.

        Returns
        -------
        Serie
            Population counts per area as a pandas Serie.
        """
        with rasterio.open(os.path.join(self.input_dir, "population.tif")) as src:
            shapes = [area.__geo_interface__ for area in areas.geometry]
            stats = zonal_stats(
                shapes,
                src.read(1, masked=True),
                affine=src.transform,
                stats=["sum"],
                nodata=src.nodata,
            )
        return pd.Series(data=[s["sum"] for s in stats], index=areas.index)

    def accessibility_stats(self, cost, areas, levels=[30, 90, 120, 150, 190]):
        """Count population having access in less than <lvl> minutes.

        Parameters
        ----------
        cost : 2d array
            Travel times in seconds.
        areas : GeoDataFrame
            Input shapes.
        levels : list of int, optional
            Time steps in minutes.

        Returns
        -------
        dict of Series
            Population counts per area and per time level.
        """
        logger.info(f"Calculating accessibility statistics for {len(areas)} areas.")
        metrics = {}
        with rasterio.open(os.path.join(self.input_dir, "population.tif")) as pop:
            time = np.zeros(shape=(pop.height, pop.width), dtype="int32")
            rasterio.warp.reproject(
                source=cost,
                destination=time,
                src_crs=self.crs,
                src_transform=self.transform,
                dst_crs=pop.crs,
                dst_transform=pop.transform,
                src_nodata=-1,
                dst_nodata=pop.nodata,
                resampling=rasterio.warp.Resampling.bilinear,
            )
            shapes = [area.__geo_interface__ for area in areas.geometry]
            for lvl in levels:
                ppp = pop.read(1, masked=True).copy()
                ppp[time > lvl * 60] = 0
                stats = zonal_stats(
                    shapes, ppp, affine=pop.transform, stats=["sum"], nodata=pop.nodata
                )
                metrics[lvl] = pd.Series(
                    data=[s["sum"] for s in stats], index=areas.index
                )
        return metrics
