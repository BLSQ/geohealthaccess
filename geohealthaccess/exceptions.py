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


class OsmiumProcessingError(GeoHealthAccessError):
    """Processing error in an Osmium subprocess."""
    def __init__(self, msg=None):
        if msg is None:
            msg = "There was an error processing the data."
        super(OsmiumProcessingError, self).__init__(msg)


class OsmiumArgumentsError(GeoHealthAccessError):
    """Command-line arguments in an Osmium subprocess are not correct."""
    def __init__(self, msg=None):
        if msg is None:
            msg = "There was a problem with the command line arguments."
        super(OsmiumArgumentsError, self).__init__(msg)
