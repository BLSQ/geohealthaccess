"""Helper functions for automatic setup of GRASS GIS.
This modules includes code from https://github.com/yannforget/shedecides
"""

import logging
import os
import shutil
import sys
import tempfile
from subprocess import run

from geohealthaccess.config import find_grass_dir
from geohealthaccess.exceptions import GrassNotFound


def find_grass_dir():
    """Try to find GRASS install directory."""
    if 'GISBASE' in os.environ:
        return os.environ['GISBASE']
    try:
        p = run(['grass', '--config', 'path'], capture_output=True)
        if p.returncode == 0 and p.stdout:
            return p.stdout.decode().strip()
        else:
            raise GrassNotFound()
    except:
        raise GrassNotFound()


# Import GRASS python modules
grass_dir = find_grass_dir()
os.environ['GISBASE'] = grass_dir
grass_module = os.path.join(grass_dir, 'etc', 'python')
if grass_module not in sys.path:
    sys.path.append(grass_module)
try:
    import grass.script as gscript
    import grass.script.setup as gsetup
except:
    raise ImportError('GRASS python modules cannot be imported.')


def check_gisdb(gisdb_path):
    """Create a GRASSDATA directory if necessary."""
    if os.path.exists(gisdb_path):
        logging.info('GRASSDATA directory already exists.')
    else:
        os.makedirs(gisdb_path)
        logging.info(f'GRASSDATA directory created at `{gisdb_path}`.')


def check_location(gisdb_path, location_name, epsg):
    """Create a GRASS location if necessary."""
    if os.path.exists(os.path.join(gisdb_path, location_name)):
        logging.info(f'Location "{location_name}" already exists.')
    else:
        gscript.core.create_location(
            gisdb_path, location_name, epsg=epsg, overwrite=False)
        logging.info(f'Location "{location_name}" created.')


def check_mapset(gisdb_path, location_name, mapset_name):
    """Create a GRASS mapset if necessary."""
    # Check if PERMANENT mapset exists
    permanent_path = os.path.join(gisdb_path, location_name, 'PERMANENT')
    if os.path.exists(permanent_path):
        # The `WIND` file is required too
        wind_path = os.path.join(permanent_path, 'WIND')
        if not os.path.exists(wind_path):
            logging.error('`PERMANENT` mapset already exists, but a `WIND` file is missing.')
        else:
            mapset_path = os.path.join(gisdb_path, location_name, mapset_name)
            if not os.path.exists(mapset_path):
                os.makedirs(mapset_path)
                shutil.copy(wind_path, os.path.join(mapset_path, 'WIND'))
                logging.info(f"'{mapset_name}' created in location '{location_name}'.")
            else:
                logging.info(f"'{mapset_name}' mapset already exists.")
    else:
        logging.error("'PERMANENT' mapset does not exist.")


def working_mapset(gisdb_path, location_name, mapset_name):
    """Launch GRASS GIS working session in the mapset."""
    mapset_path = os.path.join(gisdb_path, location_name, mapset_name)
    if os.path.exists(mapset_path):
        gsetup.init(os.environ['GISBASE'], gisdb_path, location_name, mapset_name)
        logging.info(f"Now working in mapset '{mapset_name}'.")
    else:
        logging.error(f"Mapset '{mapset_name}' does not exist at '{gisdb_path}'.")
