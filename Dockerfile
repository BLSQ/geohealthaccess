FROM ubuntu:focal-20200606

LABEL maintainer="yannforget@mailbox.org"

ENV DEBIAN_FRONTEND=noninteractive
RUN groupadd -g 1000 geohealthaccess && \
    useradd -m -s /bin/bash -u 1000 -g geohealthaccess geohealthaccess

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    locales \
    osmium-tool \
    grass-core \
    gdal-bin \
    proj-bin \
    grass-core \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/geohealthaccess
USER geohealthaccess

# Install python dependencies
COPY ./requirements.txt ./
RUN pip3 install -r requirements.txt

# Install package
COPY geohealthaccess geohealthaccess
COPY setup.py ./
COPY tests tests
RUN pip3 install -e .

ENV PATH /home/geohealthaccess/.local/bin:$PATH
ENTRYPOINT ["geohealthaccess"]
CMD ["--help"]
