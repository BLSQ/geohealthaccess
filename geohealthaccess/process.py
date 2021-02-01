import subprocess


def run(command, *, logger=None):
    """Run the provided command using subprocess.run, with sensible defaults,
    log if appropriate and return the CompletedSubprocess instance."""

    try:
        completed_process = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as e:
        if logger:
            logger(e.message)

        raise

    if logger:
        logger(
            completed_process.stdout
            if completed_process.returncode == 0
            else completed_process.stderr
        )

    return completed_process
