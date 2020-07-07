#!/usr/bin/env python3
"""Re-build Geofabrik spatial index."""

import geopandas as gpd
import requests
from rasterio.crs import CRS

from geohealthaccess.geofabrik import Region

BASE_URL = "http://download.geofabrik.de"
CONTINENTS = [
    "africa",
    "asia",
    "australia-oceania",
    "central-america",
    "europe",
    "north-america",
    "south-america",
]


def main():

    s = requests.Session()
    regions = []

    # Continent level
    for continent in CONTINENTS:
        region = Region(s, continent)
        regions.append(region)
        if not region.subregions:
            continue

        # Country level
        for subregion in region.subregions:
            region = Region(s, subregion)
            regions.append(region)
            if not region.subregions:
                continue

            # Sub-country level
            for subregion in region.subregions:
                region = Region(s, subregion)
                regions.append(region)

    sindex = gpd.GeoDataFrame(
        index=[region.id for region in regions],
        data=[region.name for region in regions],
        columns=["name"],
        geometry=[region.get_geometry() for region in regions],
        crs=CRS.from_epsg(4326),
    )

    sindex["id"] = sindex.index
    sindex.to_file("geofabrik.gpkg", driver="GPKG")


if __name__ == "__main__":
    main()
