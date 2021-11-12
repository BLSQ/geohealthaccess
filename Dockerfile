FROM ubuntu:focal-20200606

LABEL maintainer="yannforget@mailbox.org"

ENV DEBIAN_FRONTEND=noninteractive

ENV PATH=/opt/conda/bin:$PATH
ARG PATH=/opt/conda/bin:$PATH

# Dev mode
ARG DEV

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    software-properties-common \
    wget \
    ca-certificates \
    locales

RUN add-apt-repository ppa:ubuntugis/ppa && \
    apt-get update

RUN apt-get update && \
    apt-get install -y \
    osmium-tool \
    grass-core \
    grass-dev \
    gdal-bin \
    proj-bin \
    python3-six \
    && rm -rf /var/lib/apt/lists/*

# Install minio
ARG MINIO_VERSION="2021-04-06T23-11-00Z"
RUN wget -O /usr/local/bin/minio \
    https://dl.min.io/server/minio/release/linux-amd64/archive/minio.RELEASE.${MINIO_VERSION} \
    && chmod +x /usr/local/bin/minio

RUN mkdir /app

# Install miniconda
ARG MINICONDA_VERSION="py39_4.10.3"
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh \
    && mkdir -p /opt \
    && bash Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh -b -p /opt/conda \
    && rm -f Miniconda3-${MINICONDA_VERSION}-Linux-x86_64.sh

# Create and initialize conda environment
COPY environment.yml /app/
RUN conda env create -f /app/environment.yml
SHELL ["conda", "run", "-n", "geohealthaccess", "/bin/bash", "-c"]

# Install package
COPY geohealthaccess /app/geohealthaccess
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
RUN python -m pip install /app

WORKDIR /app

#RUN source /opt/conda/envs/geohealthaccess/etc/conda/activate.d/gdal-activate.sh && \
#    source /opt/conda/envs/geohealthaccess/etc/conda/activate.d/geotiff-activate.sh && \
#    source /opt/conda/envs/geohealthaccess/etc/conda/activate.d/proj4-activate.sh

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "geohealthaccess"]
CMD ["geohealthaccess", "--help"]
