from setuptools import setup, find_packages

setup(
    name="geohealthaccess",
    version="0.1",
    description="Mapping accessibility to health services",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: GIS",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.7",
    ],
    keywords="health mapping gis",
    url="https://github.com/BLSQ/geohealthaccess",
    author="Yann Forget, Grégoire Lurton",
    author_email="yannforget@mailbox.org",
    license="MIT",
    packages=find_packages(include=["geohealthaccess", "geohealthaccess.*"]),
    install_requires=[
        "appdirs",
        "beautifulsoup4",
        "click",
        "gcsfs",
        "gdal",
        "geopandas",
        "loguru",
        "numpy",
        "pandas",
        "rasterio",
        "requests",
        "requests_file",
        "s3fs",
        "shapely",
        "tqdm",
    ],
    extras_require={"dev": ["pytest", "pytest-cov", "vcrpy"]},
    package_data={
        "geohealthaccess": [
            "resources/*.geojson",
            "resources/*.json",
            "resources/*.ini",
        ]
    },
    entry_points="""
        [console_scripts]
        geohealthaccess=geohealthaccess.cli:cli
    """,
)
