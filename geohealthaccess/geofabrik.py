"""Parse Geofabrik website for automatic data acquisition."""

from datetime import datetime
import os
import re
import tempfile
from urllib.parse import urljoin, urlsplit

from appdirs import user_data_dir
from bs4 import BeautifulSoup
import geopandas as gpd
from osgeo import ogr
import requests
from shapely import wkt


BASE_URL = 'http://download.geofabrik.de'


def _header(element):
    """Find parent header of a given html element."""
    return element.find_previous(re.compile('^h[1-6]$')).text


class Page:

    def __init__(self, url):
        """Webpage to parse."""
        # Store URL and parse page
        self.url = url
        with requests.get(url) as r:
            r.encoding = 'UTF-8'
            self.soup = BeautifulSoup(r.text, 'html.parser')
        # Parse tables
        self.raw_details = None
        self.subregions = None
        self.special_subregions = None
        self.continents = None
        self.parse_tables()

    @property
    def name(self):
        """Page name."""
        return self.soup.find('h2').text


    def _parse_table(self, table):
        """Parse a BeautifulSoup table element and returns
        a list of dictionnaries (one per row).
        """
        row = table.find('tr')
        columns = [cell.text for cell in row.find_all('th')]
        datasets = []
        for row in table.find_all('tr'):
            dataset = {}
            if row.find('th'):
                continue  # skip header
            for column, cell in zip(columns, row.find_all('td')):
                content = cell.contents[0]
                if 'href' in str(content):
                    orig_path = content.attrs['href']
                    absolute_url = urljoin(self.url, orig_path)
                    relative_url = urlsplit(absolute_url).path
                    content.attrs['href'] = relative_url
                dataset[column] = cell.contents[0]
            datasets.append(dataset)
        return datasets


    def parse_tables(self):
        """Parse all tables in the page."""
        for table in self.soup.find_all('table'):
            # Raw details
            if _header(table) == 'Other Formats and Auxiliary Files':
                self.raw_details = self._parse_table(table)
            # Subregions
            elif _header(table) == 'Sub Regions':
                self.subregions = self._parse_table(table)
            # Special Subregions
            elif _header(table) == 'Special Sub Regions':
                self.special_subregions = self._parse_table(table)
            # Continents
            elif _header(table) == 'OpenStreetMap Data Extracts':
                self.continents = self._parse_table(table)


class Region:

    def __init__(self, region_id):
        self.id = region_id
        self.page = Page(self.url)
        self.name = self.page.name
        self.extent = self.get_geometry()

    @property
    def url(self):
        """URL of the region."""
        return urljoin(BASE_URL, f'{self.id}.html')

    @property
    def files(self):
        """List available files."""
        # Parsed info on datasets is contained in the
        # page.raw_details attribute.
        files_ = []
        if not self.page.raw_details:
            return None
        for f in self.page.raw_details:
            files_.append(f['file'].attrs['href'])
        return files_

    @property
    def datasets(self):
        """Summarize available datasets."""
        datasets_ = []
        for f in self.files:
            if f.endswith('.osm.pbf') and re.search('[0-9]{6}', f):
                date_str = re.search('[0-9]{6}', f).group()
                date = datetime.strptime(date_str, '%y%m%d')
                url = urljoin(self.url, f)
                datasets_.append(
                    {'date': date, 'file': f, 'url': url})
        return datasets_

    @property
    def subregions(self):
        """List available subregions."""
        # Parsed info on subregions is contained in the
        # page.subregions attribute.
        subregions_ = []
        if not self.page.subregions:
            return None
        for link in self.page.subregions:
            filename = link['Sub Region'].attrs['href']
            subregions_.append(filename.split('.')[0])
        return subregions_

    def get_geometry(self):
        """Get extent as a shapely geometry."""
        kml_fname = [f for f in self.files if f.endswith('.kml')][0]
        kml_url = urljoin(self.url, kml_fname)
        with tempfile.NamedTemporaryFile(suffix='.kml') as tmp:
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
        path = continent['Sub Region'].attrs['href']
        region_id = path.replace('.html', '')
        region = Region(region_id)
        regions.append({
            'id': region.id,
            'name': region.name,
            'geometry': region.get_geometry()
        })
        if not region.subregions:
            continue
        # Subregions
        for subregion_id in region.subregions:
            subregion = Region(subregion_id)
            regions.append({
                'id': subregion.id,
                'name': subregion.name,
                'geometry': subregion.get_geometry()
            })
            if not subregion.subregions:
                continue
            # Subsubregions
            for subsubregion_id in subregion.subregions:
                subsubregion = Region(subsubregion_id)
                regions.append({
                    'id': subsubregion.id,
                    'name': subsubregion.name,
                    'geometry': subsubregion.get_geometry()
                })
    return gpd.GeoDataFrame(regions)


def get_spatial_index(overwrite=False):
    """Load spatial index. Use existing one if available."""
    data_dir = user_data_dir(appname='GeoHealthAccess')
    expected_path = os.path.join(data_dir, 'spatial_index.gpkg')
    if os.path.isfile(expected_path) and not overwrite:
        spatial_index = gpd.read_file(expected_path)
    else:
        spatial_index = build_spatial_index()
        os.makedirs(data_dir, exist_ok=True)
        spatial_index.to_file(expected_path, driver='GPKG')
    return spatial_index[spatial_index.geometry != None]


def _cover(geom_a, geom_b):
    union = geom_a.union(geom_b)
    intersection = geom_a.intersection(geom_b)
    return round(intersection.area / union.area, 2)


def find_best_region(spatial_index, geom):
    """Find the most suited region for a given area of interest."""
    index_cover = spatial_index.copy()
    index_cover['cover'] = index_cover.geometry.apply(
        lambda x: _cover(x, geom))
    index_cover = index_cover.sort_values(by='cover', ascending=False)
    return index_cover.id.values[0], index_cover.cover.values[0]
