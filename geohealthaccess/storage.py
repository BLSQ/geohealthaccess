"""Access, read and write data from cloud storage."""

import os
import socket
import shutil

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
    def __init__(self, location):
        """Parsed location string (file path or S3/GCS URL)."""
        self.location = location

    @property
    def protocol(self):
        """Return protocol of a location."""
        parsed_url = self.location.split("://")
        if len(parsed_url) == 1:
            return "local"
        else:
            return parsed_url[0]

    @property
    def path(self):
        """Return location path (without scheme/protocol)."""
        if self.protocol == "local":
            return self.location
        else:
            return self.location.split("://")[-1]


def get_s3fs():
    """Initialize a S3 filesystem from environment variables.

    Uses the following environment variables:
        * `S3_ACCESS_KEY`
        * `S3_SECRET_KEY`
        * `S3_REGION_NAME` (defaults to "us-east-1")
        * `S3_ENDPOINT_URL` (defaults to "s3.amazonaws.com")

    If `S3_SECRET_KEY`, anonymous access is used (public buckets only).

    Returns
    -------
    fs : S3FileSystem
        A FileSystem object from s3fs.
    """
    if not has_s3fs:
        raise ImportError("s3fs library is required when using s3 urls.")
    anon = bool(os.getenv("S3_SECRET_KEY"))
    return s3fs.S3FileSystem(
        key=os.getenv("S3_ACCESS_KEY"),
        secret=os.getenv("S3_SECRET_KEY"),
        anon=anon,
        client_kwars={
            "region_name": os.getenv("S3_REGION_NAME", "us-east-1"),
            "endpoint_url": os.getenv("S3_ENDPOINT_URL", "s3.amazonaws.com"),
        },
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

    Uses the `GCS_CREDENTIALS` environment variable to locate the JSON file
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

    if os.getenv("GCE_CREDENTIALS"):
        token = os.getenv("GCE_CREDENTIALS")
    elif is_gce_instance():
        token = "cloud"
    else:
        token = "anon"

    return gcsfs.GCSFileSystem(token=token)


def ls(loc):
    """List contents of a directory.

    Simulates the behavior of os.listdir().
    """
    loc = Location(loc)

    # local
    if loc.protocol == "local":
        return os.listdir(loc.path)

    # s3
    elif loc.protocol == "s3":
        fs = get_s3fs()
        return [f.split("/")[-1] for f in fs.ls(loc.path)]

    # gcs
    elif loc.protocol == "gcs":
        fs = get_gcsfs()
        return [f.split("/")[-1] for f in fs.ls(loc.path)]

    else:
        raise IOError(f"{loc.protocol} not supported.")


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
    loc = Location(loc)

    # local
    if loc.protocol == "local":
        os.remove(loc.path)

    # s3
    elif loc.protocol == "s3":
        fs = get_s3fs()
        fs.rm(loc.path)

    # gcs
    elif loc.protocol == "gcs":
        fs = get_gcsfs()
        fs.rm(loc.path)

    else:
        raise IOError(f"{loc.protocol} protocol not supported.")


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
