import json
from pkg_resources import resource_string

from shapely.geometry import shape


def country_geometry(country_name):
    """Get the shapely geometry corresponding to a given country."""
    countries = json.loads(
        resource_string(__name__, 'resources/countries.geojson')
    )
    geom = None
    for feature in countries['features']:
        name = feature['properties']['name']
        if name == country_name:
            geom = shape(feature['geometry'])
    if not geom:
        raise ValueError('Country not found.')
    return geom
