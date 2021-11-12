"""Download administrative areas from GADM.

Notes
-----
See `<https://gadm.org/>`_ for more information about GADM.
"""

import os
import shutil
import zipfile
from tempfile import TemporaryDirectory

import requests

from geohealthaccess.utils import download_from_url

URL = "https://biogeo.ucdavis.edu/data/gadm3.6/gpkg/gadm36_{country}_gpkg.zip"


def download(country, dst_file):
    s = requests.Session()
    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        fp = download_from_url(s, URL.format(country=country.upper()), tmp_dir)
        basename = os.path.basename(fp).replace("_gpkg.zip", ".gpkg")
        with zipfile.ZipFile(fp) as z:
            z.extractall(tmp_dir)
        shutil.copyfile(os.path.join(tmp_dir, basename), dst_file)
    s.close()
    return dst_file
