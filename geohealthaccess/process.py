"""subprocess helpers"""

import subprocess


def run(args, *, logger=None):
    """Run the provided command using subprocess.run, with sensible defaults,
    log if appropriate and return the CompletedSubprocess instance."""

    try:
        completed_process = subprocess.run(
            args,
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

    if logger:
        logger(
            completed_process.stdout
            if completed_process.returncode == 0
            else completed_process.stderr
        )

    return completed_process
