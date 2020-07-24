************
Installation
************

GeoHealthAccess have three system dependencies: ``gdal`` is used to
process raster data, ``osmium-tool`` to process OpenStreetMap data and
``grass`` to perform a cost distance analysis. Alternatively, a docker
image is also available (see below).

.. code:: sh

    # Ubuntu 20.04
    sudo apt-get install gdal-bin osmium-tool grass-core

    # Fedora 32
    sudo dnf copr enable neteler/grass78
    sudo dnf update
    sudo dnf install grass grass-libs osmium-tool

.. note:: GRASS GIS builds for OSX is available on Macports, or can be downloaded on the
    `grassmac <http://grassmac.wikidot.com/downloads>`_ website.

The python package can then be installed using pip:

.. code:: sh

   # Download source code
   git clone https://github.com/BLSQ/geohealthaccess
   cd geohealthaccess
   pip install -e .

   # To install development dependencies such as pytest and sphinx:
   pip install -e .[dev]

Alternatively, a docker image is available on `Docker Hub
<https://hub.docker.com/r/yannforget/geohealthaccess>`_. See the relevant
`documentation page <docker.html>`_ for more information on how to run
GeoHealthAccess using Docker.
