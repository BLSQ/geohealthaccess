"""Helper functions for automatic data acquisition of the
Global Surface Water products.
https://global-surface-water.appspot.com/
"""


import requests
import geopandas as gpd
from rasterio.crs import CRS
from shapely.geometry import Polygon

from geohealthaccess.utils import download_from_url


BASE_URL = 'https://storage.googleapis.com/global-surface-water/downloads2'
PRODUCTS = ['occurence', 'change', 'seasonality',
            'recurrence', 'transitions', 'extent']
VERSION = '1_1'


def build_url(product, location_id):
    """Build download URL for a given tile location and product type."""
    if product not in PRODUCTS:
        raise ValueError('Invalid GSW product name.')
    return f'{BASE_URL}/{product}/{product}_{location_id}_v{VERSION}.tif'


def generate_location_id(lon, lat):
    """Generate GSW location string ID from the top left coordinates
    of the tile.
    """
    lon_str = f'{abs(lon)}{"E" if lon >= 0 else "W"}'
    lat_str = f'{abs(lat)}{"N" if lat >= 0 else "S"}'
    return f'{lon_str}_{lat_str}'


def to_geom(name):
    """Convert a given GSW tile location ID (example: '20E_0N')
    to a shapely geometry, given that:
        - The ID designates the coordinates of the top left corner
        - One tile covers a surface of 10 x 10 degrees.
    """
    lon, lat = name.split('_')
    xmin = int(lon[:-1])
    ymax = int(lat[:-1])
    if lon[-1] == 'W':
        xmin *= -1
    if lat[-1] == 'S':
        ymax *= -1
    ymin = ymax - 10
    xmax = xmin + 10
    coords = ((xmin, ymax), (xmin, ymin), (xmax, ymin),
              (xmax, ymax), (xmin, ymax))
    return Polygon(coords)


def build_tiles_index():
    """Build a geographic index of all available tiles as a geodataframe."""
    geoms = []
    names = []
    # Build a grid with 10 x 10 degrees cells
    for lon in range(-180, 180, 10):
        for lat in range(-90, 90, 10):
            coords = (
                (lon, lat + 10),
                (lon, lat),
                (lon + 10, lat),
                (lon + 10, lat + 10),
                (lon, lat + 10))
            names.append(generate_location_id(lon, lat))
            geoms.append(Polygon(coords))
    tiles_index = gpd.GeoDataFrame(index=names)
    tiles_index['geometry'] = geoms
    tiles_index.crs = CRS.from_epsg(4326)
    return tiles_index


def required_tiles(geom, product):
    """List all required tiles URLs for a given area of interest
    and product type.

    Parameters
    ----------
    geom : shapely geometry
        Area of interest in lat/lon coordinates.
    product : str
        Product type (occurence, change, seasonnality,
        recurrence, transitions or extent).
    
    Returns
    -------
    urls : list of str
        URLs of tiles required to cover the area of interest.
    """
    tiles = build_tiles_index()
    tiles = tiles[tiles.intersects(geom)]
    return [build_url(product, loc_id) for loc_id in tiles.index]


def download(geom, product, output_dir, overwrite=False):
    """Download all the GSW tiles that cover the given area of interest."""
    tiles = required_tiles(geom, product)
    with requests.Session() as s:
        for tile in tiles:
            download_from_url(s, tile, output_dir, overwrite=overwrite)