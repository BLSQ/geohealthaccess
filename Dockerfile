FROM ubuntu:18.04

LABEL maintainer="yannforget@mailbox.org"

ENV DEBIAN_FRONTEND=noninteractive
RUN groupadd -g 1000 geohealthaccess && \
    useradd -m -s /bin/bash -u 1000 -g geohealthaccess geohealthaccess

# Update & upgrade system
RUN apt-get -y update && \
    apt-get -y upgrade

# Setup locales
RUN apt-get install -y locales
RUN echo LANG="en_US.UTF-8" > /etc/default/locale
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# Install GRASS GIS and osmium
RUN apt-get install -y software-properties-common && \
    add-apt-repository -y ppa:ubuntugis/ubuntugis-unstable && \
    apt-get update && \
    apt-get install -y grass osmium-tool

# Other dependencies
RUN apt-get install -y \
    curl \
    git

# Reduce image size
RUN apt-get autoremove -y && \
    apt-get clean -y

# Install Conda package manager
WORKDIR /home/geohealthaccess
USER geohealthaccess
RUN curl -LO https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh && \
    bash Miniconda3-latest-Linux-x86_64.sh -p /home/geohealthaccess/.conda -b && \
    rm Miniconda3-latest-Linux-x86_64.sh
ENV PATH=/home/geohealthaccess/.conda/bin:${PATH}

# Pull code from github [master] and setup conda environment
RUN git clone https://github.com/BLSQ/geohealthaccess
WORKDIR /home/geohealthaccess/geohealthaccess
RUN conda env create -f environment.yml && \
    conda init bash

# Install GeoHealthAccess python package inside conda environment
RUN /bin/bash -c "source activate geohealthaccess && pip install -e ."
