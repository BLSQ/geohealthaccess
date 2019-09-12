FROM jupyter/scipy-notebook:abdb27a6dfbb
LABEL maintainer="yannforget@mailbox.org"

USER root

# Install osm2pgsql and osmosis from ubuntu repositories
RUN apt-get update && \
    apt-get install -y --no-install-recommends osm2pgsql osmosis && \
    rm -rf /var/lib/apt/lists/*

# Install more conda packages
RUN conda install --quiet --yes \
    'geopandas' \
    'shapely' \
    'psycopg2' \
    'cartopy' \
    'pyproj' \
    'tqdm'

USER $NB_UID
