"""Parse Geofabrik website for automatic data acquisition."""

import logging
import os
import re
import tempfile
from datetime import datetime
from subprocess import DEVNULL, PIPE, run
from urllib.parse import urljoin, urlsplit

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from requests_file import FileAdapter
from appdirs import user_data_dir
from bs4 import BeautifulSoup
from osgeo import ogr
from shapely import wkt

from geohealthaccess.exceptions import (
    OsmiumArgumentsError,
    OsmiumNotFound,
    OsmiumProcessingError,
)
from geohealthaccess.utils import download_from_url, human_readable_size

log = logging.getLogger(__name__)

BASE_URL = "http://download.geofabrik.de"


def _header(element):
    """Find parent header of a given html element."""
    return element.find_previous(re.compile("^h[1-6]$")).text


class Page:
    def __init__(self, url):
        """Webpage to parse."""
        # Store URL and parse page
        self.url = url
        self.sess = requests.Session()
        self.sess.mount("file://", FileAdapter())
        with self.sess.get(url) as r:
            r.encoding = "UTF-8"
            self.soup = BeautifulSoup(r.text, "html.parser")
        # Parse tables
        self.raw_details = None
        self.subregions = None
        self.special_subregions = None
        self.continents = None
        self.parse_tables()

    @property
    def name(self):
        """Page name."""
        return self.soup.find("h2").text

    def _parse_table(self, table):
        """Parse a BeautifulSoup table element and returns
        a list of dictionnaries (one per row).
        """
        row = table.find("tr")
        columns = [cell.text for cell in row.find_all("th")]
        datasets = []
        for row in table.find_all("tr"):
            dataset = {}
            if row.find("th"):
                continue  # skip header
            for column, cell in zip(columns, row.find_all("td")):
                content = cell.contents[0]
                if "href" in str(content):
                    orig_path = content.attrs["href"]
                    absolute_url = urljoin(self.url, orig_path)
                    relative_url = urlsplit(absolute_url).path
                    content.attrs["href"] = relative_url
                dataset[column] = cell.contents[0]
            datasets.append(dataset)
        return datasets

    def parse_tables(self):
        """Parse all tables in the page."""
        log.info(f"Parsing geofabrik page `{self.name}`.")
        for table in self.soup.find_all("table"):
            # Raw details
            if _header(table) == "Other Formats and Auxiliary Files":
                self.raw_details = self._parse_table(table)
            # Subregions
            elif _header(table) == "Sub Regions":
                self.subregions = self._parse_table(table)
                log.info(f"Found {len(self.subregions)} subregions.")
            # Special Subregions
            elif _header(table) == "Special Sub Regions":
                self.special_subregions = self._parse_table(table)
                log.info(f"Found {len(self.special_subregions)} special subregions.")
            # Continents
            elif _header(table) == "OpenStreetMap Data Extracts":
                self.continents = self._parse_table(table)
                log.info(f"Found {len(self.continents)} continents.")


class Region:
    def __init__(self, region_id):
        self.id = region_id
        self.page = Page(self.url)
        self.name = self.page.name
        self.extent = self.get_geometry()

    @property
    def url(self):
        """URL of the region."""
        return urljoin(BASE_URL, f"{self.id}.html")

    @property
    def files(self):
        """List available files."""
        # Parsed info on datasets is contained in the
        # page.raw_details attribute.
        files_ = []
        if not self.page.raw_details:
            return None
        for f in self.page.raw_details:
            files_.append(f["file"].attrs["href"])
        return files_

    @property
    def datasets(self):
        """Summarize available datasets."""
        datasets_ = []
        for f in self.files:
            if f.endswith(".osm.pbf") and re.search("[0-9]{6}", f):
                date_str = re.search("[0-9]{6}", f).group()
                date = datetime.strptime(date_str, "%y%m%d")
                url = urljoin(self.url, f)
                datasets_.append({"date": date, "file": f, "url": url})
        return datasets_

    @property
    def latest(self):
        """Get the URL to latest OSM dataset for the current region."""
        dates = [dataset["date"] for dataset in self.datasets]
        latest = max(dates)
        i = dates.index(latest)
        return self.datasets[i]["url"]

    @property
    def subregions(self):
        """List available subregions."""
        # Parsed info on subregions is contained in the
        # page.subregions attribute.
        subregions_ = []
        if not self.page.subregions:
            return None
        for link in self.page.subregions:
            filename = link["Sub Region"].attrs["href"]
            subregions_.append(filename.split(".")[0])
        return subregions_

    def get_geometry(self):
        """Get extent as a shapely geometry."""
        kml_fname = [f for f in self.files if f.endswith(".kml")][0]
        kml_url = urljoin(self.url, kml_fname)
        with tempfile.NamedTemporaryFile(suffix=".kml") as tmp:
            r = requests.get(kml_url)
            tmp.write(r.content)
            tmp.seek(0)
            src = ogr.Open(tmp.name)
            layer = src.GetLayer()
            feature = layer.GetFeature(1)
            geom = feature.geometry().ExportToWkt()
        return wkt.loads(geom)


def build_spatial_index():
    """Get the geometry of each available subregion and
    summarize the information as a geodataframe.
    """
    home = Page(BASE_URL)
    regions = []
    for continent in home.continents:
        path = continent["Sub Region"].attrs["href"]
        region_id = path.replace(".html", "")
        region = Region(region_id)
        regions.append(
            {"id": region.id, "name": region.name, "geometry": region.get_geometry()}
        )
        if not region.subregions:
            continue
        # Subregions
        for subregion_id in region.subregions:
            subregion = Region(subregion_id)
            regions.append(
                {
                    "id": subregion.id,
                    "name": subregion.name,
                    "geometry": subregion.get_geometry(),
                }
            )
            if not subregion.subregions:
                continue
            # Subsubregions
            for subsubregion_id in subregion.subregions:
                subsubregion = Region(subsubregion_id)
                regions.append(
                    {
                        "id": subsubregion.id,
                        "name": subsubregion.name,
                        "geometry": subsubregion.get_geometry(),
                    }
                )
    spatial_index = gpd.GeoDataFrame(regions)
    log.info(f"Created spatial index with {len(spatial_index)} records.")
    return spatial_index


def get_spatial_index(overwrite=False):
    """Load spatial index. Use existing one if available."""
    data_dir = user_data_dir(appname="GeoHealthAccess")
    expected_path = os.path.join(data_dir, "spatial_index.gpkg")
    if os.path.isfile(expected_path) and not overwrite:
        spatial_index = gpd.read_file(expected_path)
    else:
        spatial_index = build_spatial_index()
        try:
            os.makedirs(data_dir, exist_ok=True)
            spatial_index.to_file(expected_path, driver="GPKG")
        except PermissionError:
            log.warning("Unable to cache geofabrik spatial index.")
            pass
    spatial_index = spatial_index[spatial_index.geometry != None]
    return spatial_index


def _cover(geom_a, geom_b):
    union = geom_a.union(geom_b)
    intersection = geom_a.intersection(geom_b)
    return round(intersection.area / union.area, 2)


def find_best_region(spatial_index, geom):
    """Find the most suited region for a given area of interest."""
    index_cover = spatial_index.copy()
    index_cover["cover"] = index_cover.geometry.apply(lambda x: _cover(x, geom))
    index_cover = index_cover.sort_values(by="cover", ascending=False)
    region_id, cover = index_cover.id.values[0], index_cover.cover.values[0]
    log.info(f"Selected region {region_id}.")
    return region_id, cover


def check_osmium():
    """Check if osmium-tool is available."""
    check = run(["which", "osmium"], stdout=DEVNULL)
    if check.returncode == 1:
        raise OsmiumNotFound()


def _check_osmium_returncodes(process):
    """Check osmium-tool return codes and raise the relevant exception
    if needed.
    """
    if process.returncode == 1:
        raise OsmiumProcessingError(process.stderr.decode())
    elif process.returncode == 2:
        raise OsmiumArgumentsError(process.stderr.decode())
    return


def download_latest_data(region_id, dst_dir, overwrite=False):
    """Download latest OSM data for a given region identified by its ID
    in Geofabrik, as returned by the geofabrik.Region.id property.

    Parameters
    ----------
    region_id : str
        Region of interest identified by its Geofabrik ID.
    dst_dir : str
        Path to output directory.
    overwrite : bool, optional
        Forces overwrite of existing files.
    
    Returns
    -------
    osm_pbf : str
        Path to downloaded .osm.pbf file.
    """
    try:
        check_osmium()
    except OsmiumNotFound as e:
        log.exception(e)
    region = Region(region_id)
    url = region.latest
    fname = url.split("/")[-1]
    log.info(f"Downloading latest OSM data for {region.name}.")
    with requests.Session() as s:
        osm_pbf = download_from_url(s, url, dst_dir, overwrite=overwrite)
    return osm_pbf


def tags_filter(osm_pbf, dst_fname, expression, overwrite=True):
    """Extract OSM objects from an input .osm.pbf file using an Osmium tags-filter
    expression (https://docs.osmcode.org/osmium/latest/osmium-tags-filter.html).
    
    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    dst_fname : str
        Path to output .osm.pbf file.
    expression : str
        Osmium tags-filter expression. See `osmium tags-filter` manpage for details.
    overwrite : bool, optional
        Overwrite existing file.

    Returns
    -------
    dst_fname : str
        Path to output .osm.pbf file.
    """
    expression_parts = expression.split(" ")
    command = ["osmium", "tags-filter", osm_pbf]
    command += expression_parts
    command += ["-o", dst_fname]
    if overwrite:
        command += ["--overwrite"]
    log.info(f"Running command: {' '.join(command)}")
    p = run(command, stdout=PIPE, stderr=PIPE)
    _check_osmium_returncodes(p)
    src_size = human_readable_size(os.path.getsize(osm_pbf))
    dst_size = human_readable_size(os.path.getsize(dst_fname))
    log.info(
        f"Extracted {os.path.basename(dst_fname)} ({dst_size}) "
        f"from {os.path.basename(osm_pbf)} ({src_size})."
    )
    return dst_fname


def to_geojson(osm_pbf, dst_fname, overwrite=True):
    """Convert an input .osm.pbf file to a GeoJSON file.

    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    dst_fname : str
        Path to output .osm.pbf file.
    overwrite : bool, optional
        Overwrite existing file.
    
    Returns
    -------
    dst_fname : str
        Path to output GeoJSON file.
    """
    command = ["osmium", "export", osm_pbf, "-o", dst_fname]
    if overwrite:
        command += ["--overwrite"]
    log.info(f"Running command: {' '.join(command)}")
    p = run(command, stdout=PIPE, stderr=PIPE)
    _check_osmium_returncodes(p)
    src_size = human_readable_size(os.path.getsize(osm_pbf))
    dst_size = human_readable_size(os.path.getsize(dst_fname))
    log.info(
        f"Created {os.path.basename(dst_fname)} ({dst_size}) "
        f"from {os.path.basename(osm_pbf)} ({src_size})."
    )
    return dst_fname


# Osmium tags-filter expression and properties of interest for each supported
# thematic extract.
EXTRACTS = {
    "roads": {
        "expression": "w/highway",
        "properties": ["highway", "smoothness", "surface", "tracktype"],
        "geom_types": ["LineString"],
    },
    "water": {
        "expression": "nwr/natural=water nwr/waterway nwr/water",
        "properties": ["waterway", "natural", "water", "wetland", "boat"],
        "geom_types": ["LineString", "Polygon", "MultiPolygon"],
    },
    "health": {
        "expression": "nwr/amenity=clinic,doctors,hospital,dentist,pharmacy nwr/healthcare",
        "properties": ["amenity", "name", "healthcare", "dispensing", "description"],
        "geom_types": ["Point"],
    },
    "ferry": {
        "expression": "w/route=ferry",
        "properties": [
            "route",
            "duration",
            "motor_vehicle",
            "motorcar",
            "motorcycle",
            "bicycle",
            "foot",
        ],
        "geom_types": ["LineString"],
    },
}


def _centroid(geom):
    """Get centroid if possible."""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom.centroid
    return geom


def _filter_columns(geodataframe, valid_columns):
    """Filter columns of a given geodataframe."""
    n_columns = len(geodataframe.columns)
    n_removed = 0
    for column in geodataframe.columns:
        if column not in valid_columns and column != "geometry":
            geodataframe = geodataframe.drop([column], axis=1)
            n_removed += 1
    log.info(f"Removed {n_removed} columns. {len(geodataframe.columns)} remaining.")
    return geodataframe


def thematic_extract(osm_pbf, theme, dst_fname):
    """Extract a category of objects from an .osm.pbf file into a GeoPackage.

    Parameters
    ----------
    osm_pbf : str
        Path to input .osm.pbf file.
    theme : str
        Category of objects to extract (roads, water, health or ferry).
    dst_fname : str
        Path to output GeoPackage.
    
    Returns
    -------
    dst_fname : str
        Path to output GeoPackage.
    """
    if theme not in EXTRACTS:
        raise ValueError(
            f"Theme `{theme}` is not supported. Please choose one of the following "
            f"options: {', '.join(EXTRACTS.keys())}."
        )
    expression = EXTRACTS[theme.lower()]["expression"]
    properties = EXTRACTS[theme.lower()]["properties"] + ["geometry"]
    geom_types = EXTRACTS[theme.lower()]["geom_types"]
    log.info(f"Starting thematic extraction of {theme} objects...")

    with tempfile.TemporaryDirectory(prefix="geohealthaccess_") as tmpdir:

        # Filter input .osm.pbf file and export to GeoJSON with osmium-tools
        filtered = tags_filter(
            osm_pbf, os.path.join(tmpdir, "filtered.osm.pbf"), expression
        )
        intermediary = to_geojson(
            filtered, os.path.join(tmpdir, "intermediary.geojson")
        )

        # Drop useless columns
        geodf = gpd.read_file(intermediary)
        log.info(f"Loaded OSM data into a GeoDataFrame with {len(geodf)} records.")
        geodf = _filter_columns(geodf, properties)

        # Convert Polygon or MultiPolygon features to Point
        if theme == "health":
            geodf["geometry"] = geodf.geometry.apply(_centroid)
            log.info(f"Converted Polygon and MultiPolygon to Point features.")

        geodf = geodf[np.isin(geodf.geom_type, geom_types)]
        log.info(f"Removed objects with invalid geom types ({len(geodf)} remaining).")
        geodf = geodf.reset_index(drop=True)
        if not geodf.crs:
            geodf.crs = {"init": "epsg:4326"}
        geodf.to_file(dst_fname, driver="GPKG")
        dst_size = human_readable_size(os.path.getsize(dst_fname))
        log.info(
            f"Saved thematric extract into {os.path.basename(dst_fname)} "
            f"({dst_size})."
        )

    return dst_fname


