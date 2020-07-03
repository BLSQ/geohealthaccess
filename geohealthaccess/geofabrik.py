"""Parse Geofabrik website for automatic data acquisition.

The module provides a `Region` class to access Geofabrik data files for
a given region.

Examples
--------
Downloading OSM data for a geometry `geom` in `output_dir`::

    geofab = SpatialIndex()
    geofab.get()  # build the spatial index or load it from cache
    region_id, matching_score = geofab.search(geom)
    geofab.download(region_id, output_dir)

Notes
-----
See `<http://www.geofabrik.de/>`_ for more information about the Geofabrik project.
"""

import logging
import os
import re
import tempfile
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import geopandas as gpd
import requests
from appdirs import user_cache_dir
from pkg_resources import resource_filename
from bs4 import BeautifulSoup
from osgeo import ogr
from rasterio.crs import CRS
from requests_file import FileAdapter
from shapely import wkt

from geohealthaccess.utils import download_from_url

log = logging.getLogger(__name__)


class Page:
    """A Geofabrik webpage."""

    def __init__(self, url):
        """Parse a Geofabrik webpage.

        Parameters
        ----------
        url : str
            URL of the page to parse.
        """
        self.session = requests.Session()
        self.url = url
        with self.session.get(url) as r:
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

    @staticmethod
    def _header(element):
        """Find parent header of a given html element."""
        return element.find_previous(re.compile("^h[1-6]$")).text

    def _parse_table(self, table):
        """Parse an HTML data table.

        Parameters
        ----------
        table : BeautifulSoup element
            Table to parse.

        Returns
        -------
        list of dicts
            Available datasets.
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
            if self._header(table) == "Other Formats and Auxiliary Files":
                self.raw_details = self._parse_table(table)
                log.info(f"Found {len(self.raw_details)} auxiliary files.")
            # Subregions
            elif self._header(table) == "Sub Regions":
                self.subregions = self._parse_table(table)
                log.info(f"Found {len(self.subregions)} subregions.")
            # Special Subregions
            elif self._header(table) == "Special Sub Regions":
                self.special_subregions = self._parse_table(table)
                log.info(f"Found {len(self.special_subregions)} special subregions.")
            # Continents
            elif self._header(table) == "OpenStreetMap Data Extracts":
                self.continents = self._parse_table(table)
                log.info(f"Found {len(self.continents)} continents.")


class Region:
    """Geofabrik OSM region."""

    def __init__(self, region_id):
        """Initialize a Geofabrik region.

        Parameters
        ----------
        region_id : str
            Geofabrik region ID. This is the path to access the page of the region
            in the website, e.g: `africa`, `africa/kenya`, `africa/senegal-and-gambia`.
        """
        self.BASE_URL = "http://download.geofabrik.de"
        self.session = requests.Session()
        self.id = region_id
        if self.id.startswith("/"):
            self.id = self.id[1:]
        self.level = len([c for c in self.id if c == "/"])
        self.page = Page(self.url)
        self.name = self.page.name
        self.extent = self.get_geometry()

    @property
    def url(self):
        """URL of the region."""
        return urljoin(self.BASE_URL, f"{self.id}.html")

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
            r = self.session.get(kml_url)
            tmp.write(r.content)
            tmp.seek(0)
            src = ogr.Open(tmp.name)
            layer = src.GetLayer()
            feature = layer.GetFeature(1)
            geom = feature.geometry().ExportToWkt()
        return wkt.loads(geom)


class Geofabrik:
    """Geofabrik spatial index."""

    def __init__(self):
        """Initialize Geofabrik spatial index."""
        self.session = requests.Session()
        self.sindex = gpd.read_file(
            resource_filename(__name__, "resources/geofabrik.gpkg")
        )
        self.sindex.set_index(["id"], drop=True, inplace=True)

    @staticmethod
    def _match(geom_a, geom_b):
        """Calculate intersection/union ratio between two geometries."""
        union = geom_a.union(geom_b)
        intersection = geom_a.intersection(geom_b)
        return intersection.area / union.area

    def search(self, geom):
        """Find the geofabrik region ID matching a given geometry.

        Parameters
        ----------
        geom : shapely geometry
            Area of interest.

        Returns
        -------
        str
            Region ID.
        float
            Intersection ratio.
        """
        candidates = self.sindex[self.sindex.intersects(geom)].copy()
        candidates["match"] = candidates.geometry.apply(
            lambda region: self._match(region, geom)
        )
        candidates.sort_values(by="match", ascending=False, inplace=True)
        return candidates.iloc[0].name, candidates.iloc[0].match

    def download(self, region_id, output_dir, show_progress=True, overwrite=False):
        """Download OSM data for a given region.

        Parameters
        ----------
        region_id : str
            Geofabrik region ID.
        output_dir : str
            Path to output directory.
        show_progress : bool, optional
            Show download progress bar.
        overwrite : bool, optional
            Overwrite existing file.

        Returns
        -------
        str
            Path to downloaded file.
        """
        region = Region(region_id)
        log.info(f"Downloading latest OSM data for {region.name}.")
        return download_from_url(
            self.session,
            region.latest,
            output_dir,
            show_progress=show_progress,
            overwrite=overwrite,
        )
