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


def _available_files(tile_name, directory):
    """List available .tif rasters for a given tile name in a specified
    directory.
    """
    return [f for f in os.listdir(directory) if f.startswith(tile_name) and f.endswith(".tif") and "StdDev" not in f]


def download(geom, output_dir, overwrite=False):
    """Download all the CGLC tiles required to cover the area of interest."""
    tiles = required_tiles(geom)
    with requests.Session() as s:
        for tile in tiles:
            # Do not download anything if all files are already available
            fname = tile.split("/")[-1]
            tilename = fname.split("_")[0]
            available_files = _available_files(tilename, output_dir)
            if len(available_files) >= 14 and not overwrite:
                continue
            else:
                for f in available_files:
                    os.remove(os.path.join(output_dir, f))
                download_from_url(s, tile, output_dir, overwrite=overwrite)
    return output_dir


def coverfraction_layers(data_dir):
    """Get the list of tuples (layer_name, file_name) corresponding to each
    available layer.
    """
    layers = []
    for fname in os.listdir(data_dir):
        if 'coverfraction' in fname and fname.endswith('.tif'):
            file_name = os.path.join(data_dir, fname)
            layer_name = fname.split('-')[0]
            layers.append((layer_name, file_name))
    return layers
