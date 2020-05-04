# GeoHealthAccess

## Description

The `geohealthaccess` python package provides functions to acquire and process geographic data relevant to accessibility mapping, i.e. topography, land cover, surface water, population, transport networks.

### Installation

``` sh
# Download source code
git clone https://github.com/BLSQ/geohealthaccess
cd geohealthaccess

# Setup conda environment
conda env create -f environment.yml
conda activate geohealthaccess

# Install geohealthaccess package
pip install -e .
```

### Usage

``` sh
mkdir <project_dir> && cd <project_dir>
geohealthaccess-download <config_file>
geohealthaccess-preprocess <config_file>
geohealthaccess-accessibility <config_file>
```

![Processing chain](/docs/images/processing-chain.png)
: Processing chain (red=input, yellow=intermediary, green=output).

### Using Docker

``` bash
# Pull image from Docker Hub
docker pull yannforget/geohealthaccess:latest

# Go to project directory
# `config.ini` and its associated input files must be
# available in the project directory.
cd <project_dir>

# Test
docker run \
    -v "$PWD:$PWD" -w "$PWD" -u "$UID:$UID" \
    yannforget/geohealthaccess:latest \
    /bin/bash -c \
    "source activate geohealthaccess && geohealthaccess-download --help"

# Download input data
docker run \
    -v "$PWD:$PWD" -w "$PWD" -u "$UID:$UID" \
    yannforget/geohealthaccess:latest \
    /bin/bash -c \
    "source activate geohealthaccess && geohealthaccess-download config.ini"

# Preprocess input data
docker run \
    -v "$PWD:$PWD" -w "$PWD" -u "$UID:$UID" \
    yannforget/geohealthaccess:latest \
    /bin/bash -c \
    "source activate geohealthaccess && geohealthaccess-preprocess config.ini"

# Accessibility modeling
docker run \
    -v "$PWD:$PWD" -w "$PWD" -u "$UID:$UID" \
    yannforget/geohealthaccess:latest \
    /bin/bash -c \
    "source activate geohealthaccess && geohealthaccess-accessibility config.ini"
```

### Modules

* `geohealthaccess/srtm.py` : automatic downloading of 30m SRTM tiles in a given area of interest
* `geohealthaccess/utils.py` : utility functions

## Files


	├── notebooks          <- Jupyter notebooks for sharing and 
	│					discussing results     
	│
	├── references         <- Data dictionaries, manuals, and all other 
	│						explanatory materials.
	│
	├── reports            <- Generated analysis as HTML, PDF
	│
	├── src                <- Source code
	│   │
	│   ├── data_load           <- Scripts to download, preprocess and  
	│	│							clean data
	│   │
	│   ├── modeling       <-  Scripts to generate friction maps,	
	│   │		population maps and least cost analysis
	│   │
	│   ├── indicators_output    <- Scripts to generate final outputs of 
	│   │							relevance for the users
	│   └── visualization  <- Scripts to create final visualization or 
	│ 							data undelying visualizations

