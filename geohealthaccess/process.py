"""subprocess helpers"""

import os
import subprocess


GDAL_DATA = "/usr/share/gdal"
PROJ_LIB = "/usr/share/proj"


class ProcessError(Exception):
    pass


def run(args, *, logger=None):
    """Run the provided command using subprocess.run, with sensible defaults,
    log if appropriate and return the CompletedSubprocess instance."""
    
    # Make sure GDAL and PROJ env. variables are set
    env = os.environ.copy()
    env["GDAL_DATA"] = GDAL_DATA
    env["PROJ_LIB"] = PROJ_LIB

    try:
        completed_process = subprocess.run(
            args,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, ValueError) as e:
        # This only happens if subprocess.run raises an exception not linked ta a non-zero return code
        # (mostly OSError for non-existent files and ValueError if subprocess.run() is called with invalid arguments)
        if logger:
            logger(str(e))

        raise

    success = completed_process.returncode == 0

    if logger:
        logger(completed_process.stdout if success else completed_process.stderr)

    if not success:
        raise ProcessError(completed_process.stdout)

    return completed_process
