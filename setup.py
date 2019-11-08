from setuptools import setup, find_packages

setup(
    name='geohealthaccess',
    version='0.1.0',
    description='Mapping accessibility to health services',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: GIS',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7'
    ],
    keywords='health mapping gis',
    url='https://github.com/BLSQ/geohealthaccess',
    author='Yann Forget',
    author_email='yannforget@mailbox.org',
    license='MIT',
    packages=find_packages(include=['geohealthaccess', 'geohealthaccess.*']),
    install_requires=[
        'requests',
        'shapely',
        'geopandas',
        'beautifulsoup4',
        'tqdm',
        'Click',
        'rasterio'
    ],
    package_data={
        'geohealthaccess': ['resources/*.geojson', 'resources/*.json']
    },
    entry_points='''
        [console_scripts]
        geohealthaccess-download=geohealthaccess.scripts.download:download
        geohealthaccess-preprocess=geohealthaccess.scripts.preprocess:preprocess
    ''',
)
