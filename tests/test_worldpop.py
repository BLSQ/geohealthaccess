import os
import tempfile

import pytest

from geohealthaccess import worldpop


@pytest.mark.parametrize(
    "country, year, expected_url",
    [
        (
            "COD",
            2015,
            "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2015/COD/cod_ppp_2015.tif",
        ),
        (
            "COd",
            2010,
            "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2010/COD/cod_ppp_2010.tif",
        ),
        (
            "mdg",
            2018,
            "ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2018/MDG/mdg_ppp_2018.tif",
        ),
    ],
)
def test_build_url(country, year, expected_url):
    assert worldpop.build_url(country, year) == expected_url


def test_list_available_years():
    available_years = worldpop.list_available_years("TON")
    assert len(available_years) >= 20
    assert 2000 in available_years


def test__parse_worldpop_filename():
    FNAME = "ton_ppp_2016_UNadj.tif"
    datafile = worldpop._parse_worldpop_filename(FNAME)
    assert datafile.country == "ton"
    assert datafile.datatype == "ppp"
    assert datafile.prefix == "ton_ppp"
    assert datafile.year == 2016
    assert datafile.suffix == "UNadj"


def test__clean_datadir():
    # Create empty files in a temporary directory
    RASTERS = [
        "ton_ppp_2015.tif",
        "ton_ppp_2016_UNadj.tif",
        "ton_ppp_2018.tif",
        "mdg_ppp_2015.tif",
        "mdg_ppp_2017.tif",
    ]
    with tempfile.TemporaryDirectory() as tmpdir:

        # create empty files
        for raster in RASTERS:
            open(os.path.join(tmpdir, raster), "a").close()

        worldpop._clean_datadir(tmpdir)
        remaining = os.listdir(tmpdir)

        expected = ["ton_ppp_2016_UNadj.tif", "ton_ppp_2018.tif", "mdg_ppp_2017.tif"]
        assert set(remaining) == set(expected)


def test_download():
    COUNTRY = "TON"  # Tonga
    with tempfile.TemporaryDirectory() as tmpdir:

        # Simple download
        fname = worldpop.download(COUNTRY, tmpdir)
        available_years = worldpop.list_available_years(COUNTRY)
        latest = max(available_years)
        assert os.path.isfile(fname)
        assert str(latest) in os.path.basename(fname)
        mtime = os.path.getmtime(fname)

        # Should not be downloaded again
        worldpop.download(COUNTRY, tmpdir, overwrite=False)
        assert os.path.getmtime(fname) == mtime

        # Should be downloaded again
        worldpop.download(COUNTRY, tmpdir, overwrite=True)
        assert os.path.getmtime(fname) != mtime
