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
from bs4 import BeautifulSoup
from osgeo import ogr
from rasterio.crs import CRS
from requests_file import FileAdapter
from shapely import wkt

from geohealthaccess.utils import download_from_url

log = logging.getLogger(__name__)


class Page:
    """A Geofabrik webpage."""

    def __init__(self, session, url):
        """Parse a Geofabrik webpage.

        Parameters
        ----------
        session : requests session
            An open requests session object.
        url : str
            URL of the page to parse.
        """
        # Store URL and parse page
        self.url = url
        self.sess = session
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

    def __init__(self, session, region_id, parse=True):
        """Initialize a Geofabrik region.

        Parameters
        ----------
        session : requests session
            An open requests session object.
        region_id : str
            Geofabrik region ID. This is the path to access the page of the region
            in the website, e.g: `africa`, `africa/kenya`, `africa/senegal-and-gambia`.
        parse : bool, optional
            Automatically parse the page (True by default).
        """
        self.BASE_URL = "http://download.geofabrik.de"
        self.session = session
        self.id = region_id
        if parse:
            self.page = Page(self.session, self.url)
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


class SpatialIndex:
    """Geofabrik spatial index."""

    def __init__(self):
        """Initialize Geofabrik spatial index.

        Parameters
        ----------
        build_index : bool, optional
            Automatically build the spatial index. True by default.
        """
        self.BASE_URL = "http://download.geofabrik.de"
        self.CONTINENTS = [
            "africa",
            "antarctica",
            "asia",
            "australia-oceania",
            "central-america",
            "europe",
            "north-america",
            "south-america",
        ]
        self.cache_path = os.path.join(
            user_cache_dir(appname="geohealthaccess"), "geofabrik.gpkg"
        )
        self.session = requests.Session()
        self.session.mount("file://", FileAdapter())
        self.sindex = None

    def build(self):
        """Build a spatial index of Geofabrik datasets.

        Returns
        -------
        spatial_index : GeoDataFrame
            Spatial index of available regions and subregions with their id,
            their name and their geometry.

        Notes
        -----
        The function can take more than a minute to parse all the continents.
        """
        regions = []

        # Continent level
        for continent in self.CONTINENTS:
            region = Region(self.session, continent)
            regions.append(region)
            if not region.subregions:
                continue

            # Country level
            for subregion in region.subregions:
                region = Region(self.session, subregion)
                regions.append(region)
                if not region.subregions:
                    continue

                # Sub-country level
                for subregion in region.subregions:
                    region = Region(self.session, subregion)
                    regions.append(region)

        sindex = gpd.GeoDataFrame(
            index=[region.id for region in regions],
            data=[region.name for region in regions],
            columns=["name"],
            geometry=[region.get_geometry() for region in regions],
            crs=CRS.from_epsg(4326),
        )
        log.info(f"Created spatial index with {len(sindex)} records.")
        self.sindex = sindex

    def cache(self, overwrite=False):
        """Cache spatial index for future use."""
        if os.path.isfile(self.cache_path):
            if overwrite:
                log.info("Spatial index cache already exists. Removing old file.")
                os.remove(self.cache_path)
            else:
                log.info("Spatial index cache already exists. Skipping.")
                return
        cache_dir = os.path.dirname(self.cache_path)
        os.makedirs(cache_dir, exist_ok=True)
        sindex_ = self.sindex.copy()
        sindex_["id"] = sindex_.index
        log.info(f"Caching spatial index to {self.cache_path}.")
        sindex_.to_file(self.cache_path, driver="GPKG")

    def get(self, overwrite=False):
        """Build or load a cached version of the spatial index.

        Parameters
        ----------
        overwrite : bool, optional
            Overwrite cached version of the spatial index.

        Returns
        -------
        geodataframe
            Geofabrik spatial index.
        """
        if os.path.isfile(self.cache_path):
            if overwrite:
                os.remove(self.cache_path)
            else:
                sindex = gpd.read_file(self.cache_path)
                sindex = sindex.set_index(["id"], drop=True)
                self.sindex = sindex
                return
        self.build()
        self.cache(overwrite=overwrite)

    @staticmethod
    def _match(geom_a, geom_b):
        """Calculate ratio of matching intersection between two geometries."""
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
        region = Region(self.session, region_id)
        log.info(f"Downloading latest OSM data for {region.name}.")
        return download_from_url(
            self.session,
            region.latest,
            output_dir,
            show_progress=show_progress,
            overwrite=overwrite,
        )
