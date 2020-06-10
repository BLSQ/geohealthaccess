import pytest
import requests
from shapely import wkt

from geohealthaccess import srtm

# A simplified geometry of Madagascar
MADAGASCAR = (
    "POLYGON ("
    "(49.35 -12.09, 49.94 -13.03, 50.48 -15.44, 50.17 -15.98, 49.90 -15.42, "
    "49.64 -15.54, 49.84 -16.83, 47.13 -24.93, 45.15 -25.60, 44.03 -25.00, "
    "43.22 -22.25, 44.48 -19.96, 43.93 -17.48, 44.45 -16.19, 46.14 -15.70, "
    "46.47 -15.96, 46.33 -15.63, 46.95 -15.20, 46.96 -15.55, 47.23 -15.43, "
    "47.44 -14.67, 47.43 -15.11, 47.80 -14.57, 48.00 -14.76, 47.70 -14.45, "
    "48.03 -14.26, 47.90 -13.60, 48.30 -13.80, 48.78 -13.38, 48.73 -12.43, "
    "49.35 -12.09))"
)

# A simplified geometry of Tonga
TONGA = (
    "POLYGON ("
    "(-175.32 -21.12, -175.22 -21.17, -175.05 -21.15, -175.15 -21.27, -175.32 -21.12))"
)


@pytest.mark.parametrize("geom, ntiles", [(MADAGASCAR, 72), (TONGA, 1)])
def test_required_tiles(geom, ntiles):
    tiles = srtm.required_tiles(wkt.loads(geom))
    assert len(tiles) == ntiles
    for tile in tiles:
        assert tile.endswith(".hgt.zip")


@pytest.mark.http
def test_find_authenticity_token():
    with requests.Session() as s:
        r = s.get(srtm.HOMEPAGE_URL)
        token = srtm.find_authenticity_token(r.text)
    assert len(token) == 88


def test__expected_filename():
    TILE_NAME = "S16E048.SRTMGL1.hgt.zip"
    EXPECTED_FILE_NAME = "S16E048.hgt"
    assert srtm._expected_filename(TILE_NAME) == EXPECTED_FILE_NAME
