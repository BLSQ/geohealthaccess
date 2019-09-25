import json
import os
from pkg_resources import resource_string

import requests
from shapely.geometry import shape
from tqdm import tqdm


def country_geometry(country_name):
    """Get the shapely geometry corresponding to a given country."""
    countries = json.loads(
        resource_string(__name__, 'resources/countries.geojson')
    )
    geom = None
    for feature in countries['features']:
        name = feature['properties']['name']
        if name == country_name:
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
        If set to `False`, local files will not be overwritten if they have
        the same size as the remote file.

    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = url.split('/')[-1]
    local_path = os.path.join(output_dir, filename)
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        file_size = int(r.headers['Content-Length'])
        if os.path.isfile(local_path) and not overwrite:
            if os.path.getsize(local_path) == file_size:
                return local_path
        if show_progress:
            progress_bar = tqdm(
                desc=filename, total=file_size, unit_scale=True, unit='B')
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
                    if show_progress:
                        progress_bar.update(1024)
        if show_progress:
            progress_bar.close()
    return local_path
