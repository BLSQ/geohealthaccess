"""Access, read and write data from cloud storage."""

from glob import glob as local_glob
import os
import shutil
from tempfile import TemporaryDirectory
import zipfile

from loguru import logger


logger.disable(__name__)


try:
    import gcsfs

    has_gcsfs = True
except ImportError:
    has_gcsfs = False

try:
    import s3fs

    has_s3fs = True
except ImportError:
    has_s3fs = False


class Location:
    def __init__(self, path):
        """Parsed location string (file path or S3/GCS URL)."""
        self._raw_path = path

    @property
    def protocol(self):
        """Return protocol of a location."""
        parsed_url = self._raw_path.split("://")
        if len(parsed_url) == 1:
            return "local"
        else:
            return parsed_url[0]

    @property
    def path(self):
        """Return location path (without scheme/protocol)."""
        if self.protocol == "local":
            return self._raw_path
        else:
            return self._raw_path.split("://")[-1]

    def __str__(self):
        return self._raw_path


def get_s3fs():
    """Initialize a S3 filesystem from environment variables.

    Automatically uses the following environment variables:
        * `AWS_ACCESS_KEY_ID`
        * `AWS_SECRET_ACCESS_KEY`
        * `AWS_REGION` (defaults to "us-east-1")
        * `S3_ENDPOINT_URL` (defaults to "s3.amazonaws.com")

    Returns
    -------
    fs : S3FileSystem
        A FileSystem object from s3fs.
    """
    if not has_s3fs:
        raise ImportError("s3fs library is required when using s3 urls.")
    return s3fs.S3FileSystem(
        client_kwargs={
            "endpoint_url": os.getenv("S3_ENDPOINT_URL"),
        },
    )


def get_gcsfs():
    """Initialize a GCS filesystem from environment variables.

    Automatically uses the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to locate the JSON file
    containing the credentials. If the environment variable is not set, will
    fall back to the metadata service (if running within google) or
    anonymous access.

    Returns
    -------
    fs : GCSFileSystem
        A FileSystem object from gcsfs.
    """
    if not has_gcsfs:
        raise ImportError("gcsfs library is required when using GCS urls.")

    return gcsfs.GCSFileSystem()


def ls(path):
    """List contents of a directory.

    Simulates the behavior of os.listdir().
    """
    location = Location(path)
    logger.info(f"Listing files in {path}")

    # local
    if location.protocol == "local":
        return os.listdir(location.path)

    # s3
    elif location.protocol == "s3":
        fs = get_s3fs()
        return [f.split("/")[-1] for f in fs.ls(location.path)]

    # gcs
    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return [f.split("/")[-1] for f in fs.ls(location.path)]

    else:
        raise IOError(f"ls for {location} is not supported.")


def cp(src_path, dst_path):
    """Copy a file.

    Copying a file from S3 to GCS is not supported.
    """
    logger.info(f"Copying {src_path} to {dst_path}")
    src_location, dst_location = Location(src_path), Location(dst_path)

    # local
    if src_location.protocol == "local" and dst_location.protocol == "local":
        shutil.copy(src_location.path, dst_location.path)

    # from S3 to local
    elif src_location.protocol == "s3" and dst_location.protocol == "local":
        fs = get_s3fs()
        fs.get(src_location.path, dst_location.path)

    # from local to S3
    elif src_location.protocol == "local" and dst_location.protocol == "s3":
        fs = get_s3fs()
        fs.put(src_location.path, dst_location.path)

    # from S3 to S3
    elif src_location.protocol == "s3" and dst_location.protocol == "s3":
        fs = get_s3fs()
        fs.copy(src_location.path, dst_location.path)

    # from GCS to local
    elif src_location.protocol == "gcs" and dst_location.protocol == "local":
        fs = get_gcsfs()
        fs.get(src_location.path, dst_location.path)

    # from local to GCS
    elif src_location.protocol == "local" and dst_location.protocol == "gcs":
        fs = get_gcsfs()
        fs.put(src_location.path, dst_location.path)

    # from GCS to GCS
    elif src_location.protocol == "gcs" and dst_location.protocol == "gcs":
        fs = get_gcsfs()
        fs.copy(src_location.path, dst_location.path)

    else:
        raise IOError(f"cp from {src_location} to {dst_location} is not supported.")


def rm(path):
    """Remove a file."""
    location = Location(path)
    logger.info(f"Removing file {path}")

    # local
    if location.protocol == "local":
        os.remove(location.path)

    # s3
    elif location.protocol == "s3":
        fs = get_s3fs()
        fs.rm(location.path)

    # gcs
    elif location.protocol == "gcs":
        fs = get_gcsfs()
        fs.rm(location.path)

    else:
        raise IOError(f"fm for {location} is not supported.")


def mv(src_path, dst_path):
    """Move a file inside a filesystem.

    Moving files from a filesystem to another is not supported. Use
    copy() and rm() instead.
    """
    src_location, dst_location = Location(src_path), Location(dst_path)
    logger.info(f"Moving {src_path} to {dst_path}")

    # local
    if src_location.protocol == "local" and dst_location.protocol == "local":
        shutil.move(src_location.path, dst_location.path)

    # s3
    elif src_location.protocol == "s3" and dst_location.protocol == "s3":
        fs = get_s3fs()
        fs.move(src_location.path, dst_location.path)

    # gcs
    elif src_location.protocol == "gcs" and dst_location.protocol == "gcs":
        fs = get_gcsfs()
        fs.move(src_location.path, dst_location.path)

    else:
        raise IOError(f"mv from {src_location} to {dst_location} is not supported.")


def exists(path):
    """Check if a file exists."""
    location = Location(path)
    logger.info(f"Checking existence of {path}")

    # local
    if location.protocol == "local":
        return os.path.exists(location.path)

    # s3
    elif location.protocol == "s3":
        fs = get_s3fs()
        return fs.exists(location.path)

    # gcs
    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return fs.exists(location.path)

    else:
        raise IOError(f"exists for {location} is not supported.")


def mkdir(path):
    """Create directories recursively, ignore if they already exists.

    This is not needed for S3 and GCS as directories cannot be created and
    are not needed anyway.
    """
    location = Location(path)
    logger.info(f"Creating directory {path}")
    if location.protocol == "local":
        os.makedirs(location.path, exist_ok=True)


def size(path):
    """Get size of a file in bytes."""
    logger.info(f"Getting size of file {path}")
    if not exists(path):
        raise FileNotFoundError(f"No file found at {path}.")

    location = Location(path)

    if location.protocol == "local":
        return os.path.getsize(location.path)

    elif location.protocol == "s3":
        fs = get_s3fs()
        return fs.size(location.path)

    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return fs.size(location.path)

    else:
        raise IOError(f"size for {location} is not supported.")


def glob(pattern):
    """Return paths matching input pattern.

    S3 and GCS file paths are prefixed with the relevant schemes, i.e.
    s3:// or gcs://.
    """
    location = Location(pattern)

    if location.protocol == "local":
        return local_glob(location.path)

    elif location.protocol == "s3":
        fs = get_s3fs()
        return [f"s3://{path}" for path in fs.glob(location.path)]

    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return [f"gcs://{path}" for path in fs.glob(location.path)]

    else:
        raise IOError(f"glob for {location} is not supported.")


def open_(path, mode="r"):
    """Return a file-like object regardless of the file system."""
    logger.info(f"Opening file {path}")
    location = Location(path)

    if location.protocol == "local":
        return open(location.path, mode)

    elif location.protocol == "s3":
        fs = get_s3fs()
        return fs.open(location.path, mode)

    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return fs.open(location.path, mode)

    else:
        raise IOError(f"open_ for {location} is not supported.")


def unzip(src_file_path, dst_dir_path):
    """Extract contents of a .zip archive in dst_dir.

    Can read .zip file from a cloud filesystem and copy its contents
    to another cloud filesystem, but processing is performed locally.
    """
    logger.info(f"Unzipping {src_file_path} to {dst_dir_path}")
    src_file_location = Location(src_file_path)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        if src_file_location.protocol == "local":
            with zipfile.ZipFile(src_file_location.path, "r") as z:
                z.extractall(tmp_dir)

        elif src_file_location.protocol == "s3":
            fs = get_s3fs()
            with fs.open(src_file_location.path) as archive:
                with zipfile.ZipFile(archive, "r") as z:
                    z.extractall(tmp_dir)

        elif src_file_location.protocol == "gcs":
            fs = get_gcsfs()
            with fs.open(src_file_location.path) as archive:
                with zipfile.ZipFile(archive, "r") as z:
                    z.extractall(tmp_dir)

        else:
            raise IOError(f"unzip for {src_file_location} is not supported.")

        for f in os.listdir(tmp_dir):
            cp(os.path.join(tmp_dir, f), os.path.join(dst_dir_path, f))
