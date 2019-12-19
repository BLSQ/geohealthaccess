class GeoHealthAccessError(Exception):
    pass

class GrassNotFound(GeoHealthAccessError):
    """GRASS directory cannot be found."""
    def __init__(self, msg=None):
        if msg is None:
            msg = ("GRASS directory cannot be found. Please install "
                   "GRASS GIS or set the GISBASE environment variable.")
        super(GrassNotFound, self).__init__(msg)

class OsmiumNotFound(GeoHealthAccessError):
    """Osmium cannot be found."""
    def __init__(self, msg=None):
        if msg is None:
            msg = ("Osmium cannot be found. Please install osmium-tool.")
        super(OsmiumNotFound, self).__init__(msg)
