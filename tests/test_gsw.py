import os
import tempfile

import pytest
from shapely import wkt
from shapely.geometry import Polygon

from geohealthaccess import gsw


def test_build_url():
    EXPECTED = "https://storage.googleapis.com/global-surface-water/downloads2/occurrence/occurrence_180W_30S_v1_1.tif"
    assert gsw.build_url("occurrence", "180W_30S") == EXPECTED


@pytest.mark.parametrize(
    "lon, lat, expected",
    [(-180, -30, "180W_30S"), (0, 90, "0E_90N"), (-90, 60, "90W_60N")],
)
def test_generate_location_id(lon, lat, expected):
    assert gsw.generate_location_id(lon, lat) == expected


@pytest.mark.parametrize(
    "location_id, expected_geom",
    [
        (
            "180W_30S",
            "POLYGON ((-180.0 -30.0, -180.0 -40.0, -170.0 -40.0, -170.0 -30.0, -180.0 -30.0))",
        ),
        ("0E_90N", "POLYGON ((0.0 90.0, 0.0 80.0, 10.0 80.0, 10.0 90.0, 0.0 90.0))",),
        (
            "90W_60N",
            "POLYGON ((-90.0 60.0, -90.0 50.0, -80.0 50.0, -80.0 60.0, -90.0 60.0))",
        ),
    ],
)
def test_to_geom(location_id, expected_geom):
    expected_geom = wkt.loads(expected_geom)
    assert gsw.to_geom(location_id).almost_equals(expected_geom, decimal=1)


def test_build_tiles_index():
    idx = gsw.build_tiles_index()
    assert len(idx) == 648
    assert isinstance(idx.geometry[0], Polygon)


MADAGASCAR = (
    "MULTIPOLYGON ("
    "((49.8 -17.1, 49.9 -16.9, 50.0 -16.7, 50.0 -16.9, 49.8 -17.1)), "
    "((48.3 -13.3, 48.4 -13.4, 48.2 -13.4, 48.2 -13.3, 48.3 -13.3)), "
    "((49.4 -12.1, 50.5 -15.4, 47.1 -24.9, 45.1 -25.6, 43.2 -22.3, 43.9 -17.5, 49.4 -12.1)))"
)


def test_required_tiles():
    EXPECTED_TILES = [
        "https://storage.googleapis.com/global-surface-water/downloads2/seasonality/seasonality_40E_30S_v1_1.tif",
        "https://storage.googleapis.com/global-surface-water/downloads2/seasonality/seasonality_40E_20S_v1_1.tif",
        "https://storage.googleapis.com/global-surface-water/downloads2/seasonality/seasonality_50E_20S_v1_1.tif",
    ]
    tiles = gsw.required_tiles(wkt.loads(MADAGASCAR), "seasonality")
    assert set(tiles) == set(EXPECTED_TILES)


@pytest.mark.http
def test_download():
    mdg = wkt.loads(MADAGASCAR)
    PRODUCT = "seasonality"

    with tempfile.TemporaryDirectory() as tmpdir:

        # Simple download
        gsw.download(mdg, PRODUCT, tmpdir)
        fname = os.path.join(tmpdir, os.listdir(tmpdir)[0])
        assert os.path.isfile(fname)
        mtime = os.path.getmtime(fname)

        # Should not be downloaded again
        gsw.download(mdg, PRODUCT, tmpdir, overwrite=False)
        assert os.path.getmtime(fname) == mtime

        # Should be downloaded again
        gsw.download(mdg, PRODUCT, tmpdir, overwrite=True)
        assert os.path.getmtime(fname) != mtime
