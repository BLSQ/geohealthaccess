*************
CLI Reference
*************

The command-line interface of GeoHealthAccess provides three sub-commands:

1. ``download`` fetches input datasets from various open-access sources
2. ``preprocess`` merges, reprojects and aligns input rasters into a common shape,
   extent and CRS
3. ``access`` models travel speeds and computes travel times.

For each sub-command, if ``output-dir`` option is not provided, a default
directory is created under ``<current_dir>/Data``.

.. click:: geohealthaccess.cli:download
  :prog: geohealthaccess download

.. click:: geohealthaccess.cli:preprocess
  :prog: geohealthaccess preprocess

.. click:: geohealthaccess.cli:access
  :prog: geohealthaccess access
