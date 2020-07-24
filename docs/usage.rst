*****
Usage
*****

The ``geohealthaccess`` program is divided into three commands:

-  ``download`` for automatic data acquisition
-  ``preprocess`` for preprocessing of input data
-  ``access`` to compute travel times

.. code:: sh

   geohealthaccess --help

::

   Usage: geohealthaccess [OPTIONS] COMMAND [ARGS]...

     Map accessibility to health services.

   Options:
     --help  Show this message and exit.

   Commands:
     access      Map travel times to the provided health facilities.
     download    Download input datasets.
     preprocess  Preprocess and co-register input datasets.

Data acquisition
~~~~~~~~~~~~~~~~

.. note:: NASA EarthData credentials are required to download SRTM tiles. An
   account can be created on the `EarthData
   <https://urs.earthdata.nasa.gov/users/new>`_ website.

.. code:: sh

   geohealthaccess download --help

::

   Usage: geohealthaccess download [OPTIONS]

     Download input datasets.

   Options:
     -c, --country TEXT         ISO A3 country code  [required]
     -o, --output-dir PATH      Output directory
     -u, --earthdata-user TEXT  NASA EarthData username  [required]
     -p, --earthdata-pass TEXT  NASA EarthData password  [required]
     -f, --overwrite            Overwrite existing files
     --help                     Show this message and exit.

.. note:: If ``output-dir`` is not provided, files will be written to
   ``./Data/Input``.

NASA EarthData credentials can also be set using environment variables:

.. code:: sh

   export EARTHDATA_USERNAME=<your_username>
   export EARTHDATA_PASSWORD=<your_password>

Preprocessing
~~~~~~~~~~~~~

.. code:: sh

   geohealthaccess preprocess --help

::

   Usage: geohealthaccess preprocess [OPTIONS]

     Preprocess and co-register input datasets.

   Options:
     -c, --country TEXT      ISO A3 country code  [required]
     -s, --crs TEXT          CRS as a PROJ4 string  [required]
     -r, --resolution FLOAT  Pixel size in `crs` units
     -i, --input-dir PATH    Input data directory
     -o, --output-dir PATH   Output data directory
     -f, --overwrite         Overwrite existing files
     --help                  Show this message and exit.

.. note:: If not specified, ``input-dir`` will be set to ``./Data/Input`` and
   ``output-dir`` to ``./Data/Intermediary``.

Modeling
~~~~~~~~

.. code:: sh

   geohealthaccess access --help

::

   Usage: geohealthaccess access [OPTIONS]

     Map travel times to the provided health facilities.

   Options:
     -i, --input-dir PATH      Input data directory
     -o, --output-dir PATH     Output data directory
     --car / --no-car          Enable/disable car scenario
     --walk / --no-walk        Enable/disable walk scenario
     --bike / --no-bike        Enable/disable bike scenario
     -s, --travel-speeds PATH  JSON file with custom travel speeds
     -d, --destinations PATH   Destination points (GeoJSON or Geopackage)
     -f, --overwrite           Overwrite existing files
     --help                    Show this message and exit.

.. note:: If not specified, ``input-dir`` is set to ``./Data/Intermediary`` and
   ``output-dir`` to ``./Data/Output``. By default, only the ``car``
   scenario is enabled and if no ``destinations`` are provided, health
   facilities extracted from OpenStreetMap will be used as target points
   for the cost distance analysis. Likewise, default values for travel
   speeds are used if the ``--travel-speeds`` option is not set.

Three output rasters are created for each enabled scenario and provided
destination points:

-  ``cost_<scenario>_<destinations>.tif`` : cumulated cost (or travel
   time, in minutes) to reach the nearest ``destinations`` feature.
-  ``nearest_<scenario>_<destinations>.tif`` : ID of the nearest
   ``destinations`` feature.
-  and ``backlink_<scenario>_<destinations>.tif`` : backlink raster.
