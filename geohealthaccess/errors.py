"""Exceptions and warnings."""


class GeoHealthAccessError(Exception):
    """Root exception class."""


class MissingDataError(GeoHealthAccessError):
    """Raised when data are missing."""


class BadDataError(GeoHealthAccessError):
    """Raised when data appear incomplete or corrupted."""


class OsmiumNotFoundError(GeoHealthAccessError):
    """Raised when osmium executable cannot be found."""
