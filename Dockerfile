FROM ubuntu:focal-20200606

LABEL maintainer="yannforget@mailbox.org"

ENV DEBIAN_FRONTEND=noninteractive

# Dev mode
ARG DEV

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    locales \
    osmium-tool \
    grass-core \
    gdal-bin \
    libgdal-dev \
    proj-bin \
    grass-core \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir /app

# Install python dependencies
RUN pip3 install --upgrade pip
COPY requirements.txt /app/
RUN pip3 install -r /app/requirements.txt

# Dev dependencies
COPY requirements-dev.txt /app/
RUN if [ "$DEV" = "true" ] ; then pip3 install -r /app/requirements-dev.txt ; fi

# Install package
COPY geohealthaccess /app/geohealthaccess
COPY tests /app/tests
COPY setup.py /app/
RUN pip3 install -e /app

ENV GDAL_DATA=/usr/share/gdal

WORKDIR /app
ENTRYPOINT ["geohealthaccess"]
CMD ["--help"]
