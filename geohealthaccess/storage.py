"""Access, read and write data from cloud storage."""

from glob import glob as local_glob
import os
import socket
import shutil
from tempfile import TemporaryDirectory
import zipfile

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
    def __init__(self, loc):
        """Parsed location string (file path or S3/GCS URL)."""
        self.loc = loc

    @property
    def protocol(self):
        """Return protocol of a location."""
        parsed_url = self.loc.split("://")
        if len(parsed_url) == 1:
            return "local"
        else:
            return parsed_url[0]

    @property
    def path(self):
        """Return location path (without scheme/protocol)."""
        if self.protocol == "local":
            return self.loc
        else:
            return self.loc.split("://")[-1]


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
        client_kwargs={"endpoint_url": os.getenv("S3_ENDPOINT_URL"),},
    )


def is_gce_instance():
    """Check if code is running inside a GCE instance.

    Via DNS lookup to metadata server.
    """
    try:
        socket.getaddrinfo("metadata.google.internal", 80)
    except socket.gaierror:
        return False
    return True


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


def ls(loc):
    """List contents of a directory.

    Simulates the behavior of os.listdir().
    """
    location = Location(loc)

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
        raise IOError(f"{location.protocol} not supported.")


def cp(src, dst):
    """Copy a file.

    Copying a file from S3 to GCS is not supported.
    """
    src, dst = Location(src), Location(dst)

    # local
    if src.protocol == "local" and dst.protocol == "local":
        shutil.copy(src.path, dst.path)

    # from S3 to local
    elif src.protocol == "s3" and dst.protocol == "local":
        fs = get_s3fs()
        fs.get(src.path, dst.path)

    # from local to S3
    elif src.protocol == "local" and dst.protocol == "s3":
        fs = get_s3fs()
        fs.put(src.path, dst.path)

    # from S3 to S3
    elif src.protocol == "s3" and dst.protocol == "s3":
        fs = get_s3fs()
        fs.copy(src.path, dst.path)

    # from GCS to local
    elif src.protocol == "gcs" and dst.protocol == "local":
        fs = get_gcsfs()
        fs.get(src.path, dst.path)

    # from local to GCS
    elif src.protocol == "local" and dst.protocol == "gcs":
        fs = get_gcsfs()
        fs.put(src.path, dst.path)

    # from GCS to GCS
    elif src.protocol == "gcs" and dst.protocol == "gcs":
        fs = get_gcsfs()
        fs.copy(src.path, dst.path)

    else:
        raise IOError(f"File copy from {src.protocol} to {dst.protocol} not supported.")


def rm(loc):
    """Remove a file."""
    location = Location(loc)

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
        raise IOError(f"{location.protocol} protocol not supported.")


def mv(src, dst):
    """Move a file inside a filesystem.

    Moving files from a filesystem to another is not supported. Use
    copy() and rm() instead.
    """
    src, dst = Location(src), Location(dst)

    # local
    if src.protocol == "local" and dst.protocol == "local":
        shutil.move(src.path, dst.path)

    # s3
    elif src.protocol == "s3" and dst.protocol == "s3":
        fs = get_s3fs()
        fs.move(src.path, dst.path)

    # gcs
    elif src.protocol == "gcs" and dst.protocol == "gcs":
        fs = get_gcsfs()
        fs.move(src.path, dst.path)

    else:
        raise IOError(
            f"Moving files from {src.protocol} to {dst.protocol} not supported."
        )


def exists(loc):
    """Check if a file exists."""
    location = Location(loc)

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
        raise IOError(
            f'The "{location.protocol}" protocol is not supported ({location}).'
        )


def mkdir(loc):
    """Create directories recursively, ignore if they already exists.

    This is not needed for S3 and GCS as directories cannot be created and
    are not needed anyway.
    """
    location = Location(loc)
    if location.protocol == "local":
        os.makedirs(location.path, exist_ok=True)


def size(loc):
    """Get size of a file in bytes."""
    location = Location(loc)
    if not exists(location.location):
        raise FileNotFoundError(f"No file found at {location.location}.")

    if location.protocol == "local":
        return os.path.getsize(location.path)

    elif location.protocol == "s3":
        fs = get_s3fs()
        return fs.size(location.path)

    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return fs.size(location.path)

    else:
        raise IOError(f"{location.protocol} not supported.")


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
        raise IOError(f"{location.protocol} not supported.")


def open_(loc, mode="r"):
    """Return a file-like object regardless of the file system."""
    location = Location(loc)

    if location.protocol == "local":
        return open(location.path, mode)

    elif location.protocol == "s3":
        fs = get_s3fs()
        return fs.open(location.path, mode)

    elif location.protocol == "gcs":
        fs = get_gcsfs()
        return fs.open(location.path, mode)

    else:
        raise IOError(f"{location.protocol} not supported.")


def unzip(src_file, dst_dir):
    """Extract contents of a .zip archive in dst_dir.

    Can read .zip file from a cloud filesystem and copy its contents
    to another cloud filesystem, but processing is performed locally.
    """
    src_file, dst_dir = Location(src_file), Location(dst_dir)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:

        if src_file.protocol == "local":
            with zipfile.ZipFile(src_file.path, "r") as z:
                z.extractall(tmp_dir)

        elif src_file.protocol == "s3":
            fs = get_s3fs()
            with fs.open(src_file.path) as archive:
                with zipfile.ZipFile(archive, "r") as z:
                    z.extractall(tmp_dir)

        elif src_file.protocol == "gcs":
            fs = get_gcsfs()
            with fs.open(src_file.path) as archive:
                with zipfile.ZipFile(archive, "r") as z:
                    z.extractall(tmp_dir)

        else:
            raise IOError(f"{src_file.protocol} not supported.")

        for f in os.listdir(tmp_dir):
            cp(os.path.join(tmp_dir, f), os.path.join(dst_dir.location, f))
