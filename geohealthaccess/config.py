import configparser
import os
from pkg_resources import resource_string
from subprocess import run

from appdirs import user_data_dir

from geohealthaccess.exceptions import GrassNotFound


DATA_DIR = user_data_dir(appname='geoaccesshealth')


def default_config():
    """Get default configuration."""
    return resource_string(__name__, 'resources/config.ini')


def write_default_config():
    """Write default configuration file to disk."""
    config_path = os.path.join(DATA_DIR, 'default_config.ini')
    with open(config_path, 'w') as f:
        f.write(default_config())


def find_grass_dir():
    """Try to find GRASS install directory."""
    if 'GISBASE' in os.environ:
        return os.environ['GISBASE']
    try:
        p = run(['grass', '--config', 'path'], capture_output=True)
        if p.returncode == 0:
            return p.stdout.decode().strip()
        else:
            raise GrassNotFound()
    except:
        raise GrassNotFound()


def load_config(config_path):
    """Load user configuration file."""
    config = configparser.ConfigParser()
    config.read(config_path)

    # Make relative paths absolute
    root_dir = os.path.abspath(os.path.dirname(config_path))
    for key, directory in config['DIRECTORIES'].items():
        if not os.path.isabs(directory):
            config['DIRECTORIES'][key] = os.path.join(root_dir, directory)
    if not os.path.isabs(config['MODELING']['LandCoverSpeeds']):
        config['MODELING']['LandCoverSpeeds'] = os.path.join(
            root_dir, config['MODELING']['LandCoverSpeeds'])
    if not os.path.isabs(config['MODELING']['RoadNetworkSpeeds']):
        config['MODELING']['RoadNetworkSpeeds'] = os.path.join(
            root_dir, config['MODELING']['RoadNetworkSpeeds'])
    for key, directory in config['DESTINATIONS'].items():
        if not os.path.isabs(directory):
            config['DESTINATIONS'][key] = os.path.join(root_dir, directory)

    # Guess GRASS directory if not provided
    if 'GRASS' not in config:
        config.add_section('GRASS')
    if 'GrassDir' not in config['GRASS']:
        config['GRASS']['GrassDir'] = find_grass_dir()

    # NASA Earthdata credentials
    if 'EARTHDATA' not in config:
        config.add_section('EARTHDATA')
    if 'EarthdataUsername' not in config['EARTHDATA']:
        username = os.environ.get('EARTHDATA_USERNAME', '')
        config['EARTHDATA']['EarthdataUsername'] = username
    if 'EarthdataPassword' not in config['EARTHDATA']:
        password = os.environ.get('EARTHDATA_PASSWORD', '')
        config['EARTHDATA']['EarthdataPassword'] = password

    # Write changes to disk
    with open(config_path, 'w') as f:
        config.write(f)

    return config
