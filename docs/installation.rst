************
Installation
************

Python package
==============

The ``geohealthaccess`` python package can be installed using `Conda
<https://www.anaconda.com/distribution/>`_ and pip:

.. code-block:: sh

    git clone https://github.com/BLSQ/geohealthaccess
    cd geohealthaccess

    # Setup conda environment
    conda env create -f environment.yml
    conda activate geohealthaccess

    # Install python package in the conda environment
    pip install -e .

Dependencies
============

Two additional dependencies are required in order to run the program: `osmium
<https://osmcode.org/osmium-tool/>`_ and `GRASS GIS <https://grass.osgeo.org/>`_
(>= 7.7). Please refer to their official documentation for installation
instructions.

Ubuntu
******

.. code-block:: sh

    sudo apt-get install software-properties-common
    sudo add-apt-repository ppa:ubuntugis/ubuntugis-unstable
    sudo apt-get update
    sudo apt-get install grass osmium-tool

Fedora
******

.. code-block:: sh

    sudo dnf copr enable neteler/grass78
    sudo dnf update
    sudo dnf install grass grass-libs osmium-tool

Docker image
============

TODO.
