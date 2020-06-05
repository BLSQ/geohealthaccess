import pytest

from geohealthaccess import worldpop


@pytest.mark.parametrize('country, year, expected_url', [
    ('COD', 2015, 'ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2015/COD/cod_ppp_2015.tif'),
    ('COd', 2010, 'ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2010/COD/cod_ppp_2010.tif'),
    ('mdg', 2018, 'ftp://ftp.worldpop.org.uk/GIS/Population/Global_2000_2020/2018/MDG/mdg_ppp_2018.tif')
])
def test_build_url(country, year, expected_url):
    assert worldpop.build_url(country, year) == expected_url
