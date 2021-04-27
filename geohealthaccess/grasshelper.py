"""Helper functions for automatic setup of GRASS GIS.
This modules includes code from https://github.com/yannforget/shedecides
"""

import os
import shutil
import subprocess
import sys

from loguru import logger

from geohealthaccess.errors import GrassNotFoundError

logger.disable(__name__)


def find_grass_dir():
    """Try to find GRASS install directory."""
    if "GISBASE" in os.environ:
        return os.environ["GISBASE"]
    p = subprocess.run(["grass", "--config", "path"], capture_output=True)
    if p.returncode == 0:
        return p.stdout.decode().strip()
    else:
        raise GrassNotFoundError()


# Import GRASS python modules
grass_dir = find_grass_dir()
os.environ["GISBASE"] = grass_dir
grass_module = os.path.join(grass_dir, "etc", "python")
if grass_module not in sys.path:
    sys.path.append(grass_module)
try:
    import grass.script as gscript
    import grass.script.setup as gsetup
except ImportError:
    raise ImportError("GRASS python modules cannot be imported.")


def check_gisdb(gisdb_path):
    """Create a GRASSDATA directory if necessary."""
    if os.path.exists(gisdb_path):
        logger.info("GRASSDATA directory already exists.")
    else:
        os.makedirs(gisdb_path)
        logger.info(f"GRASSDATA directory created at `{gisdb_path}`.")


def check_location(gisdb_path, location_name, crs):
    """Create a GRASS location if necessary."""
    if os.path.exists(os.path.join(gisdb_path, location_name)):
        logger.info(f'Location "{location_name}" already exists.')
    else:
        if crs.is_epsg_code:
            gscript.core.create_location(
                gisdb_path,
                location_name,
                epsg=crs.to_epsg(),
                overwrite=False,
            )
        else:
            gscript.core.create_location(
                gisdb_path,
                location_name,
                proj4=crs.to_proj4(),
                overwrite=False,
            )
        logger.info(f'Location "{location_name}" created.')


def check_mapset(gisdb_path, location_name, mapset_name):
    """Create a GRASS mapset if necessary."""
    # Check if PERMANENT mapset exists
    permanent_path = os.path.join(gisdb_path, location_name, "PERMANENT")
    if os.path.exists(permanent_path):
        # The `WIND` file is required too
        wind_path = os.path.join(permanent_path, "WIND")
        if not os.path.exists(wind_path):
            logger.error(
                "`PERMANENT` mapset already exists, but a `WIND` file is missing."
            )
        else:
            mapset_path = os.path.join(gisdb_path, location_name, mapset_name)
            if not os.path.exists(mapset_path):
                os.makedirs(mapset_path)
                shutil.copy(wind_path, os.path.join(mapset_path, "WIND"))
                logger.info(f"'{mapset_name}' created in location '{location_name}'.")
            else:
                logger.info(f"'{mapset_name}' mapset already exists.")
    else:
        logger.error("'PERMANENT' mapset does not exist.")


def working_mapset(gisdb_path, location_name, mapset_name):
    """Launch GRASS GIS working session in the mapset."""
    mapset_path = os.path.join(gisdb_path, location_name, mapset_name)
    if os.path.exists(mapset_path):
        gsetup.init(os.environ["GISBASE"], gisdb_path, location_name, mapset_name)
        logger.info(f"Now working in mapset '{mapset_name}'.")
    else:
        logger.error(f"Mapset '{mapset_name}' does not exist at '{gisdb_path}'.")


def setup_environment(gisdb, crs):
    """Setup environment variables for GRASS GIS and its Python modules.
    Documentation: https://grass.osgeo.org/grass76/manuals/variables.html.
    Then setup a basic GRASS environment.

    Parameters
    ----------
    gisdb : str
        Path to GRASS data dir.
    crs : CRS object
        CRS of the GRASS location as a rasterio CRS object.
    """
    LOCATION = "GEOHEALTHACCESS"
    MAPSET = "PERMANENT"
    if "GISBASE" not in os.environ:
        os.environ["GISBASE"] = find_grass_dir()
    logger.info(f'GISBASE = {os.environ["GISBASE"]}.')

    if "GISRC" not in os.environ:
        os.environ["GISRC"] = os.path.join(os.environ["HOME"], ".gisrc")
    gscript.setup.init(
        gisbase=os.environ["GISBASE"],
        dbase=gisdb,
        location=LOCATION,
        mapset=MAPSET,
    )
    logger.info(f'GISRC = {os.environ["GISRC"]}.')

    grass_python_path = os.path.join(os.environ["GISBASE"], "etc", "python")
    if grass_python_path not in sys.path:
        sys.path.append(grass_python_path)
    logger.info(f"Importing GRASS Python module from {grass_python_path}.")

    check_gisdb(gisdb)
    check_location(gisdb, LOCATION, crs)
    check_mapset(gisdb, LOCATION, MAPSET)
    logger.info("GRASS environment initialized.")

    return


def grass_execute(*args, **kwargs):
    """Execute a GRASS command and return stdout and stderr."""
    kwargs["stdout"] = gscript.PIPE
    kwargs["stderr"] = gscript.PIPE
    ps = gscript.start_command(*args, **kwargs)
    cmd_output = ps.communicate()
    log_cmd_output(cmd_output)
    return cmd_output


def log_cmd_output(cmd_output):
    """Log stdout and stderr from gscript.start_command()."""
    if not cmd_output:
        return
    stdout, stderr = cmd_output

    # stdout
    if stdout:
        stdout = stdout.decode("UTF-8")
        for line in stdout.split("\n"):
            line = line.strip()
            # skip empty lines and progress bar
            if line and "\x08" not in line:
                logger.debug(line)

    # stderr
    if stderr:
        stderr = stderr.decode("UTF-8")
        for line in stderr.split("\n"):
            line = line.strip()
            # skip empty lines and progress bar
            if line and "\x08" not in line:
                logger.debug(line)
