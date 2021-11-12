"""Tests for worldpop module."""


import os
from tempfile import TemporaryDirectory

import requests

from geohealthaccess import worldpop


def test_build_url():

    assert worldpop.build_url("ben", 2020, un_adj=True) == (
        "https://data.worldpop.org/GIS/Population/Global_2000_2020/"
        "2020/BEN/ben_ppp_2020_UNadj.tif"
    )

    assert worldpop.build_url("ben", 2019, un_adj=False) == (
        "https://data.worldpop.org/GIS/Population/Global_2000_2020/"
        "2019/BEN/ben_ppp_2019.tif"
    )


def test_download(monkeypatch):
    def mockreturn(self, chunk_size):
        return [b"", b"", b""]

    monkeypatch.setattr(requests.Response, "iter_content", mockreturn)

    with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
        fp = worldpop.download(
            "ben", tmp_dir, 2020, un_adj=True, show_progress=False, overwrite=False
        )
        assert os.path.isfile(fp)
        assert os.path.basename(fp) == "ben_ppp_2020_UNadj.tif"
