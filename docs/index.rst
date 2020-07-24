*********************************************************
GeoHealthAccess: mapping accessibility to health services
*********************************************************


.. figure:: https://raw.githubusercontent.com/BLSQ/geohealthaccess/master/docs/images/travel-times-example.png
   :alt: Travel times to the nearest health facility.
   :height: 200px
   :align: center

Modeling population accessibility to health facilities has always been tedious
and time-consuming. From the selection of relevant data sources to the modeling
in itself, a wide range of skills and software solutions are required.
GeoHealthAccess is a tool that aims to automate the process using a set of high
resolution, global and open datasets – in order to enable fast and automated
country-scaled analysis. To that end, input datasets are automatically pulled
from various sources:

-  `Geofabrik <https://www.geofabrik.de>`__ (OpenStreetMap) for the
   transport network ;
-  `Copernicus Global Land Cover <https://lcviewer.vito.be/>`__ for land
   cover ;
-  `Global Surface Water <https://global-surface-water.appspot.com/>`__
   for surface water ;
-  `Shuttle Radar Topography
   Mission <https://www2.jpl.nasa.gov/srtm/>`__ for topography ;
-  and `WorldPop <https://www.worldpop.org/>`__ for population maps.



.. toctree::
   :maxdepth: 2
   :caption: Contents

   installation
   docker
   usage
   examples
   methodology
   cli
   api


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
