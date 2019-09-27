"""Helper functions for automatic data acquisition of the
Copernicus Global Land Cover product.
https://lcviewer.vito.be/
"""

import os

import requests
from rasterio.crs import CRS
from shapely.geometry import Polygon
import geopandas as gpd

from geohealthaccess.utils import download_from_url


# A manifest text file keeps track of all the URLs of the available tiles
MANIFEST_URL = 'https://s3-eu-west-1.amazonaws.com/vito-lcv/2015/ZIPfiles/manifest_cgls_lc_v2_100m_global_2015.txt'


def tile_name(url):
    """Extract tile name from URL."""
    filename = url.split('/')[-1]
    return filename.split('_')[0]


def to_geom(name):
    """Convert a given land cover tile name to a geometry.
    Tile name is composed of the 3-digit longitude and 2-digit
    latitude of the top-left corner (example: "W180N80").
    """
    xmin = int(name[1:4])
    ymax = int(name[5:7])
    if name[0] == 'W':
        xmin *= -1
    if name[4] == 'S':
        ymax *= -1
    ymin = ymax - 20
    xmax = xmin + 20
    coords = ((xmin, ymax), (xmin, ymin), (xmax, ymin),
              (xmax, ymax), (xmin, ymax))
    return Polygon(coords)


def build_tiles_index():
    """Build the tiles index as a geodataframe."""
    # Build a list of URLs
    urls = requests.get(MANIFEST_URL).text.split('\r\n')
    # Ignore empty URLs
    urls = [url for url in urls if url]
    # Build the geodataframe
    tiles = gpd.GeoDataFrame(
        index=[tile_name(url) for url in urls],
        crs=CRS.from_epsg(4326))
    tiles['url'] = urls
    tiles['geometry'] = [to_geom(name) for name in tiles.index]
    return tiles


def required_tiles(geom):
    """Get the URLs of the tiles required to cover a given
    area of interest.
    """
    tiles_index = build_tiles_index()
    tiles = tiles_index[tiles_index.intersects(geom)]
    return list(tiles.url)


def download(geom, output_dir, overwrite=False):
    """Download all the CGLC tiles required to cover the area of interest."""
    tiles = required_tiles(geom)
    with requests.Session() as s:
        for tile in tiles:
            download_from_url(s, tile, output_dir, overwrite=overwrite)
    return output_dir
