***************
Getting Started
***************

GeoHealthAccess provides three different command-line tools to perform an
accessibility analysis over a given area of interest:
``geohealthaccess-download``, ``geohealthaccess-preprocess`` and
``geohealthaccess-accessibility``.

.. code-block:: sh

    $ geohealthaccess-download --help

    usage: geohealthaccess-download [-h] config_file

    positional arguments:
    config_file  .ini configuration file

    optional arguments:
    -h, --help   show this help message and exit


.. code-block:: sh

    $ geohealthaccess-preprocess --help

    usage: geohealthaccess-preprocess [-h] [--remove] config_file

    positional arguments:
    config_file  .ini configuration file

    optional arguments:
    -h, --help   show this help message and exit
    --remove     remove raw data from disk after preprocessing


.. code-block:: sh

    $ geohealthaccess-accessibility --help

    usage: geohealthaccess-accessibility [-h] config_file

    positional arguments:
    config_file  .ini configuration file

    optional arguments:
    -h, --help   show this help message and exit

