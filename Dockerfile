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
    wget \
    ca-certificates \
    locales \
    osmium-tool \
    grass-core \
    gdal-bin \
    proj-bin \
    python3-six \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /app

# Install miniconda
ARG MINICONDA_VERSION="py38_4.9.2"
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
COPY setup.py /app/
RUN pip3 install -e /app

WORKDIR /app
ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "geohealthaccess", "python", "-m", "geohealthaccess.cli"]
CMD ["--help"]
