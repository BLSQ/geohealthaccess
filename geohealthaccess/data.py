"""Access input, intermediary and output data."""

from pathlib import Path


def as_list(func):
    """Get list of absolute paths as strings instead of Path objects."""

    def wrapper(*args, **kwargs):
        """Make paths absolute and convert them to strings."""
        paths = func(*args, **kwargs)
        return [p.resolve().as_posix() for p in paths]

    return wrapper


def check_path(func):
    """Return None if output path does not exist."""

    def wrapper(*args, **kwargs):
        """Return absolute path as string if it exists. If not, return None."""
        path = func(*args, **kwargs)
        if path.is_file():
            return path.resolve().as_posix()
        else:
            return None

    return wrapper


class Data:
    """Access datasets in a directory."""

    def __init__(self, data_dir):
        """Initialize data access."""
        self.dir = Path(data_dir)


class Raw(Data):
    """Access raw datasets."""

    @property
    @as_list
    def population(self):
        """Get population files."""
        return self.dir.glob("Population/*ppp*.tif")

    @property
    @as_list
    def land_cover(self):
        """Get land cover files."""
        return self.dir.glob("Land_Cover/*LC100*.zip")

    @property
    @as_list
    def elevation(self):
        """Get elevation files."""
        return self.dir.glob("Elevation/*SRTM*.hgt.zip")

    @property
    @as_list
    def openstreetmap(self):
        """Get raw OSM files."""
        return self.dir.glob("OpenStreetMap/*.osm.pbf")

    @property
    @as_list
    def surface_water(self):
        """Get raw surface water files."""
        return self.dir.glob("Surface_Water/seasonality*.tif")


class Intermediary(Data):
    """Access intermediary data."""

    @property
    @check_path
    def aspect(self):
        """Get aspect raster."""
        return self.dir.joinpath("aspect.tif")

    @property
    @check_path
    def elevation(self):
        """Get elevation raster."""
        return self.dir.joinpath("elevation.tif")

    @property
    @check_path
    def health(self):
        """Get OSM health objects."""
        return self.dir.joinpath("health.gpkg")

    @property
    @check_path
    def land_cover(self):
        """Get land cover raster stack."""
        return self.dir.joinpath("land_cover.tif")

    @property
    @check_path
    def population(self):
        """Get population raster."""
        return self.dir.joinpath("population.tif")

    @property
    @check_path
    def roads(self):
        """Get OSM road objects."""
        return self.dir.joinpath("roads.gpkg")

    @property
    @check_path
    def slope(self):
        """Get slope raster."""
        return self.dir.joinpath("slope.tif")

    @property
    @check_path
    def surface_water(self):
        """Get surface water raster."""
        return self.dir.joinpath("surface_water.tif")

    @property
    @check_path
    def osm_water(self):
        """Get OSM water objects."""
        return self.dir.joinpath("water.gpkg")

    @property
    @check_path
    def osm_water_raster(self):
        """Get rasterized OSM water objects."""
        return self.dir.joinpath("water_osm.tif")

    @property
    @check_path
    def ferry(self):
        """Get OSM ferry routes."""
        return self.dir.joinpath("ferry.gpkg")
