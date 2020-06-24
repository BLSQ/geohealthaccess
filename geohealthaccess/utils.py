"""Utility functions."""

import json
import logging
import os
import zipfile
from urllib.parse import urlparse

from pkg_resources import resource_string
from shapely.geometry import shape
from tqdm.auto import tqdm

log = logging.getLogger(__name__)


def human_readable_size(size, decimals=1):
    """Transform size in bytes into human readable text."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1000:
            break
        size /= 1000
    return f"{size:.{decimals}f} {unit}"


def size_from_url(session, url):
    """Get size of a distant file based on HTTP headers.

    Parameters
    ----------
    session : requests session
        Initialized requests session object.
    url : str
        URL of the file.

    Returns
    -------
    size : int
        Size in bytes.
    """
    r = session.head(url, allow_redirects=True, headers={"Accept-Encoding": "identity"})
    content_length = r.headers.get("Content-Length")
    return int(content_length)


def http_same_size(session, url, fname):
    """Compare local and remote sizes of a file.

    Parameters
    ----------
    session : requests session"osmium" "citation" "openstreetmap"
        An initialized requests session object.
    url : str
        URL of the file.
    fname : str
        Path to local file.
    """
    if not os.path.isfile(fname):
        return False
    remote_size = size_from_url(session, url)
    local_size = os.path.getsize(fname)
    return remote_size == local_size


def country_geometry(country):
    """Get the shapely geometry corresponding to a given country
    identified by its name or its three-letters ISO A3 Code.
    """
    countries = json.loads(resource_string(__name__, "resources/countries.geojson"))
    geom = None
    for feature in countries["features"]:
        name = feature["properties"]["ADMIN"]
        code = feature["properties"]["ISO_A3"]
        if country.lower() in (name.lower(), code.lower()):
            geom = shape(feature["geometry"])
    if not geom:
        raise ValueError("Country not found.")
    return geom


def download_from_url(
    session, url, output_dir, show_progress=True, overwrite=False, pbar_position=0
):
    """Download remote file from URL in a given requests session.

    Params
    ------
    session : requests.Session()
        An authentified requests session object.
    url : str
        Full URL of the file to be downloaded.
    output_dir : str
        Path to output directory. Local filename is guessed from the URL.
    show_progress : bool, optional (default=True)
        Show a progress bar.
    overwrite : bool, optional (default=False)
        If set to `True`, output file will be removed before download.
    pbar_position : int, optional (default=0)
        Optionally set the absolute position of the progress bar in case several
        threads display a progress bar simultaneously.

    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = url.split("/")[-1]
    local_path = os.path.join(output_dir, filename)

    with session.get(url, stream=True, timeout=5) as r:

        try:
            r.raise_for_status()
        except Exception as e:
            log.error(e)

        # Remove old file if overwrite
        if os.path.isfile(local_path) and overwrite:
            log.info(f"Removing old {filename} file.")
            os.remove(local_path)

        # Skip download if remote and local sizes are equal
        if http_same_size(session, url, local_path):
            log.info(
                f"Remote and local sizes of {filename} are equal. Skipping download."
            )
            return local_path

        # Setup progress bar
        if show_progress:
            size = int(r.headers.get("Content-Length"))
            bar_format = "{desc} | {percentage:3.0f}% | {rate_fmt}"
            progress_bar = tqdm(
                desc=filename,
                bar_format=bar_format,
                total=size,
                unit_scale=True,
                unit="B",
                leave=False,
                position=pbar_position,
            )

        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    if show_progress:
                        progress_bar.update(1024)

        if show_progress:
            progress_bar.close()

    filesize = human_readable_size(os.path.getsize(local_path))
    log.info(f"Downloaded file {filename} ({filesize}).")

    return local_path


def download_from_ftp(ftp, url, output_dir, show_progress=True, overwrite=False):
    """Download a file from a public FTP server.

    Parameters
    ----------
    ftp : FTP
        A logged-in ftplib.FTP session.
    url : str
        Path to remote file (ftp://<ftp_server>/<dir>/<file>).
    output_dir : str
        Path to local output directory.
    show_progress : bool, optional
        Show download progress bar.
    overwrite : bool, optional
        Overwrite local file.

    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    url = urlparse(url)
    if url.scheme != "ftp":
        raise ValueError("Invalid FTP URL.")

    size = ftp.size(url.path)
    fname = url.path.split("/")[-1]
    local_path = os.path.join(output_dir, fname)

    # Remove old file if overwrite
    if os.path.isfile(local_path) and overwrite:
        log.info(f"File {fname} already exists. Removing it.")
        os.remove(local_path)

    # Do not download again if local and remote file sizes are equal
    if os.path.isfile(local_path):
        if os.path.getsize(local_path) == size:
            log.info(f"File {fname} already exists. Skipping download.")
            return local_path
        else:
            log.info(
                f"File {fname} already exists but size differs. Removing old file."
            )
            os.remove(local_path)

    log.info(f"Downloading {fname} to {local_path}.")
    if show_progress:
        progress = tqdm(total=size, desc=fname, unit_scale=True, unit="B")

    with open(local_path, "wb") as f:

        def write_and_progress(chunk):
            """Write chunk to disk and update the progress bar."""
            f.write(chunk)
            if show_progress:
                progress.update(len(chunk))

        ftp.retrbinary(f"RETR {url.path}", write_and_progress)

    size = human_readable_size(os.path.getsize(local_path))
    log.info(f"Downloaded {fname} ({size}).")
    if show_progress:
        progress.close()
    return local_path


def size_from_ftp(ftp, url):
    """Get size of a file on an FTP server.

    Parameters
    ----------
    ftp : FTP
        An open ftplib FTP session.
    url : str
        File URL.

    Returns
    -------
    int
        Size in bytes.
    """
    url = urlparse(url)
    return ftp.size(url.path)


def unzip(src, dst_dir=None):
    """Extract a .zip archive."""
    if not dst_dir:
        dst_dir = os.path.dirname(src)
    with zipfile.ZipFile(src, "r") as z:
        z.extractall(dst_dir)
    return dst_dir


def unzip_all(src_dir, remove_archives=False):
    """Unzip all .zip files in a directory."""
    filenames = os.listdir(src_dir)
    filenames = [f for f in filenames if f.endswith(".zip")]
    progress = tqdm(total=len(filenames))
    for filename in filenames:
        filename = os.path.join(src_dir, filename)
        unzip(filename)
        if remove_archives:
            os.remove(filename)
        progress.update(1)
    progress.close()
    return src_dir
