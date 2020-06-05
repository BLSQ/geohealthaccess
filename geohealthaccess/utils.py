import json
import logging
from time import ctime
from datetime import datetime
import os
from ftplib import FTP, error_reply
from pkg_resources import resource_string
from urllib.parse import urlparse
import zipfile

import requests
from shapely.geometry import shape
from tqdm.auto import tqdm


log = logging.getLogger(__name__)


def human_readable_size(size, decimals=1):
    """Transform size in bytes into human readable text."""
    for unit in ['B','KB','MB','GB','TB']:
        if size < 1000:
            break
        size /= 1000
    return f'{size:.{decimals}f} {unit}'


def http_same_size(url, fname, session=None):
    """Compare remote and local sizes using the Content-Length
    HTTP header.
    """
    if not os.path.isfile(fname):
        return False
    headers = {'Accept-Encoding': 'identity'}
    if session:
        r = session.head(url, allow_redirects=True, headers=headers)
    else:
        r = requests.head(url, allow_redirects=True, headers=headers)
    content_length = int(r.headers.get('Content-Length'))
    local_size = os.path.getsize(fname)
    return content_length == local_size


def http_newer(url, fname, session=None):
    """Compare Last-Modified HTTP header and file metadata to
    check for changes.
    """
    if not os.path.isfile(fname):
        return True
    if session:
        r = session.head(url, allow_redirects=True)
    else:
        r = requests.head(url, allow_redirects=True)

    mtime_http = datetime.strptime(
        r.headers.get('Last-Modified'),
        '%a, %d %b %Y %H:%M:%S %Z'
    )

    mtime_local = datetime.strptime(
        ctime(os.path.getmtime(fname)),
        '%a %b %d %H:%M:%S %Y'
    )
    
    return mtime_http > mtime_local


def country_geometry(country):
    """Get the shapely geometry corresponding to a given country
    identified by its name or its three-letters ISO A3 Code.
    """
    countries = json.loads(
        resource_string(__name__, 'resources/countries.geojson'))
    geom = None
    for feature in countries['features']:
        name = feature['properties']['ADMIN']
        code = feature['properties']['ISO_A3']
        if country.lower() in (name.lower(), code.lower()):
            geom = shape(feature['geometry'])
    if not geom:
        raise ValueError('Country not found.')
    return geom


def download_from_url(session, url, output_dir, show_progress=True,
                      overwrite=False):
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

    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = url.split('/')[-1]
    local_path = os.path.join(output_dir, filename)

    with session.get(url, stream=True, timeout=5) as r:

        try:
            r.raise_for_status()
        except Exception as e:
            log.error(e)
        
        # Remove old file if overwrite
        if os.path.isfile(local_path) and overwrite:
            log.info(f'Removing old {filename} file.')
            os.remove(local_path)

        # Skip download if remote and local sizes are equal
        if http_same_size(url, local_path, session):
            log.info(f'Remote and local sizes of {filename} are equal. Skipping download.')
            return local_path

        # Setup progress bar
        if show_progress:
            size = int(r.headers.get('Content-Length'))
            progress_bar = tqdm(
                desc=filename, total=size, unit_scale=True, unit='B')

        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    if show_progress:
                        progress_bar.update(1024)

        if show_progress:
            progress_bar.close()
    
    filesize = human_readable_size(os.path.getsize(local_path))
    log.info(f'Downloaded file {filename} ({filesize}).')

    return local_path


def _check_ftp_login(ftp):
    """Check if FTP login was successfull. If not, raise
    an exception.
    """
    if ftp.lastresp == '230':
        return True
    else:
        raise error_reply('FTP login error.')


def download_from_ftp(url, output_dir, overwrite=False):
    """Download a file from a public FTP server.

    Parameters
    ----------
    url : str
        Path to remote file (ftp://<ftp_server>/<dir>/<file>).
    output_dir : str
        Path to local output directory.
    overwrite : bool, optional
        Overwrite local file.
    
    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    url = urlparse(url)
    ftp = FTP(url.netloc)
    ftp.login()

    # Check if login was successfull
    try:
        _check_ftp_login(ftp)
    except error_reply as e:
        log.exception(e)
    else:
        log.info(f'Logged-in to FTP {url.netloc}.')

    parts = url.path.split('/')
    filename = parts[-1]
    directory = '/'.join(parts[:-1])
    ftp.cwd(directory)
    file_size = ftp.size(filename)
    local_path = os.path.join(output_dir, filename)

    # Remove old file if overwrite
    if os.path.isfile(local_path) and overwrite:
        log.info(f'File {filename} already exists. Removing it.')
        os.remove(local_path)
    
    # Do not download again if local and remote file sizes are equal
    if os.path.isfile(local_path):
        if os.path.getsize(local_path) == file_size:
            log.info(f'File {filename} already exists. Skipping download.')
            return local_path
        else:
            log.info(f'File {filename} already exists but size differs. Removing old file.')
            os.remove(local_path)

    log.info(f'Downloading {url} to {local_path}.')
    progress = tqdm(total=file_size, desc=filename, unit_scale=True, unit='B')

    with open(local_path, 'wb') as f:

        def write_and_progress(chunk):
            """Custom callback function that write data chunk to disk
            and update the progress bar accordingly.
            """
            f.write(chunk)
            progress.update(len(chunk))
        
        ftp.retrbinary(f'RETR {filename}', write_and_progress)
    
    size = human_readable_size(os.path.getsize(local_path))
    log.info(f'Downloaded {filename} ({size}).')
    progress.close()
    ftp.close()
    return local_path


def unzip(src, dst_dir=None):
    """Extract a .zip archive."""
    if not dst_dir:
        dst_dir = os.path.dirname(src)
    with zipfile.ZipFile(src, 'r') as z:
        z.extractall(dst_dir)
    return dst_dir


def unzip_all(src_dir, remove_archives=False):
    """Unzip all .zip files in a directory."""
    filenames = os.listdir(src_dir)
    filenames = [f for f in filenames if f.endswith('.zip')]
    progress = tqdm(total=len(filenames))
    for filename in filenames:
        filename = os.path.join(src_dir, filename)
        unzip(filename)
        if remove_archives:
            os.remove(filename)
        progress.update(1)
    progress.close()
    return src_dir
