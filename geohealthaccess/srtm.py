"""Download and preprocess elevation data from the SRTM."""

import os
import json
from pkg_resources import resource_string, resource_filename

import requests
from shapely.geometry import shape, mapping
import geopandas as gpd
from bs4 import BeautifulSoup
from tqdm import tqdm


HOMEPAGE_URL = 'https://urs.earthdata.nasa.gov'
LOGIN_URL = 'https://urs.earthdata.nasa.gov/login'
PROFILE_URL = 'https://urs.earthdata.nasa.gov/profile'
DOWNLOAD_URL = 'http://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/'


def required_tiles(geom):
    """Get the list of SRTM tiles required to cover a given
    area of interest.

    Params
    ------
    geom : shapely geometry
        The area of interest.
    
    Returns
    -------
    tiles : list
        List of the SRTM tiles (filenames) that intersects the area
        of interest.
    """
    tiles = gpd.read_file(
        resource_filename(__name__, 'resources/srtm.geojson')
    )
    tiles = tiles[tiles.intersects(geom)]
    return list(tiles.dataFile)


def find_authenticity_token(login_page):
    """Find authentiticy token in EarthData homepage.
    Required to log in.

    Params
    ------
    login_page : str
        HTML source code of the login page.
    
    Returns
    -------
    token : str
        Authenticity token.
    """
    soup = BeautifulSoup(login_page, 'html.parser')
    token = ''
    for element in soup.find_all('input'):
        if element.attrs.get('name') == 'authenticity_token':
            token = element.attrs.get('value')
    if not token:
        raise ValueError('Token not found in EarthData login page.')
    return token


def logged_in(login_response):
    """Check if log-in to EarthData succeeded based
    on cookie values.

    Params
    ------
    login_response : request object
        Response to the login POST request.
    
    Returns
    -------
    user_logged : bool
        `True` if the login was successfull.
    """
    response_cookies = login_response.cookies.get_dict()
    user_logged = response_cookies.get('urs_user_already_logged')
    return user_logged == 'yes'


def authentify(session, username, password):
    """Authentify a requests session by logging into NASA EarthData platform.

    Params
    ------
    session : requests.Session()
        An initialized requests session object.
    username : str
        NASA EarthData username.
    password : str
        NASA EarthData password.
    
    Returns
    -------
    session : requests.Session()
        Updated requests session object with authentified cookies
        and headers.
    """
    r = session.get(HOMEPAGE_URL)
    r.raise_for_status()
    token = find_authenticity_token(r.text)
    payload = {
        'username': username,
        'password': password,
        'authenticity_token': token
    }
    r = session.post(LOGIN_URL, data=payload)
    r.raise_for_status()
    if not logged_in(r):
        raise requests.exceptions.ConnectionError('Log-in to EarthData failed.')
    return session


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
        Overwrite existing files.
    
    Returns
    -------
    local_path : str
        Local path to downloaded file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = url.split('/')[-1]
    local_path = os.path.join(output_dir, filename)
    if os.path.isfile(local_path) and not overwrite:
        return local_path
    with session.get(url, stream=True) as r:
        r.raise_for_status()
        file_size = int(r.headers['Content-Length'])
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


def download(geom, output_dir, username, password, show_progress=True,
             overwrite=False):
    """Download the SRTM tiles that intersects the area of interest.

    Params
    ------
    geom : shapely geometry
        Area of interest.
    output_dir : str
        Output directory where SRTM tiles will be downloaded.
    username : str
        NASA EarthData username.
    password : str
        NASA EarthData password.
    show_progress : bool, optional (default=True)
        Show progress bars.
    overwrite : bool, optional (default=False)
        Overwrite existing files.
    
    Returns
    -------
    tiles : list of str
        List of downloaded SRTM tiles.
    """
    tiles = required_tiles(geom)
    with requests.Session() as session:
        authentify(session, username, password)
        for tile in tiles:
            url = DOWNLOAD_URL + tile
            download_from_url(
                session, url, output_dir, show_progress overwrite)
    return tiles
