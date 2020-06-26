"""Access input, intermediary and output data."""

from pathlib import Path


def as_list(func):
    """Get list of absolute paths as strings instead of Path objects."""

    def wrapper(*args, **kwargs):
        """Make paths absolute and convert them to strings."""
        paths = func(*args, **kwargs)
        return [p.resolve().as_posix() for p in paths]

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
