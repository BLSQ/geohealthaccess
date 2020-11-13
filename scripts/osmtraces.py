#!/usr/bin/env python3
"""Download GPS traces from OpenStreetMap for a given country."""

import os

import click
import requests
import gpxpy
import geopandas as gpd
from shapely.geometry import Point, Polygon
import numpy as np
from tqdm import tqdm
from rasterio.crs import CRS

from geohealthaccess.utils import country_geometry


def get_gps_traces(geom):
    """Get GPS traces from OSM intersecting a given geometry.

    Parameters
    ----------
    geom : shapely geometry
        Area of interest.

    Returns
    -------
    traces : str
        GPS traces in GPX format as a raw XML string.
    """
    ENDPOINT = "https://api.openstreetmap.org/api/0.6/"
    xmin, ymin, xmax, ymax = geom.bounds
    query = f"trackpoints?bbox={xmin},{ymin},{xmax},{ymax}&page=0"
    with requests.get(ENDPOINT + query, stream=True) as r:
        if not r.status_code == 200:
            raise requests.exceptions.HTTPError(r.text)
        xml = r.text
    return xml


def create_grid(geom):
    """Get 0.25° x 0.25° cells in a given area of interest.

    This is because OSM API does not allow requesting data for larger areas
    of interest.

    Parameters
    ----------
    geom : shapely geometry
        Area of interest.

    Returns
    -------
    cells : list of geometries
        0.25° cells as a list of polygon geometries.
    """
    xmin, ymin, xmax, ymax = geom.bounds
    width = int(np.ceil((xmax - xmin) / 0.25))
    height = int(np.ceil((ymax - ymin) / 0.25))
    dx, dy = 0.25, 0.25
    cells = []
    for i in range(width):
        for j in range(height):
            cells.append(
                Polygon(
                    [
                        (xmin + i * dx, ymin + j * dy),
                        (xmin + i * dx + dx, ymin + j * dy),
                        (xmin + i * dx + dx, ymin + j * dy + dy),
                        (xmin + i * dx, ymin + j * dy + dy),
                    ]
                )
            )
    return [c for c in cells if c.intersects(geom)]


@click.command()
@click.option("--country", "-c", type=str, help="ISO A3 country code")
@click.option("--output-dir", "-o", type=click.Path(), help="output directory")
def osm_traces(country, output_dir):
    """Download and parse user-uploaded OSM GPS traces for a given country."""
    output_dir = os.path.join(output_dir, country.lower())
    os.makedirs(output_dir, exist_ok=True)
    geom = country_geometry(country)
    cells = create_grid(geom)
    pbar = tqdm(total=len(cells))
    crs = CRS.from_epsg(4326)
    for cell_i, cell in enumerate(cells):
        fname = os.path.join(output_dir, f"{str(cell_i).zfill(5)}.geojson")
        if os.path.exists(fname):
            pbar.update(1)
            continue
        trackid = 0
        data = gpd.GeoDataFrame(columns=["trackid", "speed", "geometry"])
        data.crs = crs
        xml = get_gps_traces(cell)
        gpx = gpxpy.parse(xml)
        for track in gpx.tracks:
            for segment in track.segments:
                for point_i, point in enumerate(segment.points):
                    if segment.get_speed(point_i):
                        data = data.append(
                            {
                                "trackid": trackid,
                                "speed": segment.get_speed(point_i),
                                "geometry": Point(point.longitude, point.latitude),
                            },
                            ignore_index=True,
                        )
            trackid += 1
        pbar.update(1)
        if len(data):
            data.to_file(fname, driver="GeoJSON")
        else:
            # Just create an empty file to keep track of which
            # cells have been processed
            with open(fname, "w") as f:
                pass
    pbar.close()
    return


if __name__ == "__main__":
    osm_traces()
