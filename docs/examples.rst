********
Examples
********

Creating a map of travel times to the nearest health facility for
Burundi:

.. code:: sh

   # Download input datasets
   geohealthaccess download \
       --country BDI \
       --earthdata-user <your_username> \
       --earthdata-pass <your_password>

   # Preprocess input datasets to a common raster grid
   geohealthaccess preprocess \
       --country BDI \
       --crs "EPSG:3857" \
       --resolution 100

   # Compute travel times to nearest health facility for the `car` and `walk`
   # scenarios.
   geohealthaccess access --car --walk

   # Or use your own data for destinations:
   geohealthaccess access --car --walk -d hospitals.geojson -d clinics.geojson
