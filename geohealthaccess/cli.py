"""GeoHealthAccess command-line interface.

Examples
--------
Getting help::

    geohealthaccess --help

Getting help for a specific subcommand::

    geohealthaccess download --help
    geohealthaccess preprocess --help
    geohealthaccess access --help
"""

from geohealthaccess.errors import GeoHealthAccessError
import os
import click
import json
import geopandas as gpd
import rasterio
import pytest
from tempfile import TemporaryDirectory

from geohealthaccess import storage, gadm
from geohealthaccess.geohealthaccess import GeoHealthAccess


@click.group()
def cli():
    """Map accessibility to health services."""
    pass


@cli.command()
def test():
    """Run test suite."""
    pytest.main(["tests"])


@cli.command()
@click.option("--country", "-c", required=True, type=str, help="iso a3 country code")
@click.option(
    "--output-dir", "-o", required=True, type=click.Path(), help="output directory"
)
@click.option(
    "--logs-dir", "-l", required=False, type=click.Path(), help="logs directory"
)
@click.option(
    "--earthdata-username",
    "-u",
    required=True,
    envvar="EARTHDATA_USERNAME",
    help="earthdata username",
)
@click.option(
    "--earthdata-password",
    "-w",
    required=True,
    envvar="EARTHDATA_PASSWORD",
    help="earthdata password",
)
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="overwrite existing files"
)
def download(
    country, output_dir, earthdata_username, earthdata_password, logs_dir, overwrite
):
    """Download input datasets."""
    # no need to set input_dir and output_dir as they are not gonna be used
    gha = GeoHealthAccess(
        raw_dir=output_dir,
        input_dir=None,
        output_dir=None,
        country=country,
        logs_dir=logs_dir,
    )

    # cache remote raw_dir if needed
    gha.cache(show_progress=True, overwrite=overwrite)

    gha.download(
        earthdata_username=earthdata_username,
        earthdata_password=earthdata_password,
        show_progress=True,
        overwrite=overwrite,
    )

    # upload cache to remote raw_dir if needed
    gha.upload(show_progress=True, overwrite=overwrite)


@cli.command()
@click.option("--country", "-c", type=str, required=True, help="ISO A3 country code")
@click.option(
    "--input-dir", "-i", required=True, type=click.Path(), help="input directory"
)
@click.option(
    "--output-dir", "-o", required=True, type=click.Path(), help="output directory"
)
@click.option("--crs", "-s", type=str, default="EPSG:3857", help="target CRS")
@click.option("--resolution", "-r", type=int, default=100, help="pixel size")
@click.option("--logs-dir", "-l", type=click.Path(), help="logs directory")
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="overwrite existing files"
)
def preprocess(input_dir, output_dir, crs, resolution, country, logs_dir, overwrite):
    """Preprocess and co-register input datasets."""
    gha = GeoHealthAccess(
        raw_dir=input_dir,
        input_dir=output_dir,
        output_dir=None,
        country=country,
        crs=rasterio.crs.CRS.from_string(crs),
        resolution=resolution,
        logs_dir=logs_dir,
    )

    # cache from remote data directories if needed
    gha.cache(show_progress=True, overwrite=overwrite)

    # run preprocessing routines
    gha.preprocessing(show_progress=True, overwrite=overwrite)

    # dump spatial information into a json file so that it can be
    # re-used by `geohealthaccess access`
    gha.dump_spatial_info()

    # upload cache to remote data directories if needed
    gha.upload(show_progress=True, overwrite=overwrite)


@cli.command()
@click.option("--country", "-c", type=str, required=True, help="ISO A3 country code")
@click.option("--input-dir", "-i", type=click.Path(), help="input directory")
@click.option("--output-dir", "-o", type=click.Path(), help="output directory")
@click.option("--car/--no-car", default=True, help="enable or disable car scenario")
@click.option("--walk/--no-walk", default=False, help="enable or disable walk scenario")
@click.option("--bike/--no-bike", default=False, help="enable or disable bike scenario")
@click.option(
    "--areas", "-a", type=click.Path(), required=False, help="custom zonal statistics"
)
@click.option(
    "--moving-speeds",
    "-s",
    type=click.Path(),
    help="json file with custom moving speeds",
)
@click.option(
    "--target",
    "-t",
    type=click.Path(),
    multiple=True,
    help="target points",
)
@click.option("--logs-dir", "-l", type=click.Path(), help="logs directory")
@click.option(
    "--overwrite", "-f", is_flag=True, default=False, help="overwrite existing files"
)
def access(
    country,
    input_dir,
    output_dir,
    car,
    walk,
    bike,
    areas,
    moving_speeds,
    target,
    logs_dir,
    overwrite,
):
    """Map travel times to the provided health facilities."""
    # raw_dir is not needed anymore as data has already been pre-processed
    gha = GeoHealthAccess(
        raw_dir=None,
        input_dir=input_dir,
        output_dir=output_dir,
        country=country,
        logs_dir=logs_dir,
    )

    # cache remote data directories if needed
    gha.cache(show_progress=True, overwrite=overwrite)

    # update spatial attributes from a preprocess() dump in input_dir
    # this is to avoid asking again for CRS, area of interest and resolution
    gha.update_spatial_info()

    # update moving speeds if a custom file is provided
    if moving_speeds:
        with storage.open_(moving_speeds) as f:
            gha.moving_speeds = json.load(f)

    # load areas for computation of zonal statistics
    # if no file is provided, download administrative areas
    if areas:
        # areas can be a local, s3 or gcs path
        # and may be provided as a GeoJSON or GPKG
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            areas_tmp = os.path.join(tmp_dir, os.path.basename(areas))
            storage.cp(areas, areas_tmp)
            if areas.lower().endswith(".geojson") or areas.lower().endswith(".json"):
                areas = gpd.read_file(areas_tmp, driver="GeoJSON")
            elif areas.lower().endswith(".gpkg"):
                areas = gpd.read_file(areas_tmp, driver="GPKG")
            else:
                raise GeoHealthAccessError(
                    f"{os.path.basename(areas)} is not a supported file format."
                )
    else:
        with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
            dst_file = gadm.download(gha.country, os.path.join(tmp_dir, "areas.gpkg"))
            areas = gpd.read_file(dst_file, layer=1)

    # if not target points are provided, use health facilities from OSM
    if not target:
        target = [os.path.join(gha.input_dir, "health.gpkg")]

    modes = []
    if car:
        modes.append("car")
    if walk:
        modes.append("walk")
    if bike:
        modes.append("bike")

    for mode in modes:

        friction = gha.friction_surface(mode=mode)

        for target_ in target:

            # load start_points as a geodataframe
            with TemporaryDirectory(prefix="geohealthaccess_") as tmp_dir:
                target_tmp = os.path.join(tmp_dir, os.path.basename(target_))
                storage.cp(target_, target_tmp)
                points = gpd.read_file(target_tmp)

            # create sub-directory based on mode and target
            label = os.path.basename(target_).split(".")[0]
            dst_dir = os.path.join(gha.output_dir, label, mode)
            os.makedirs(dst_dir, exist_ok=True)

            if mode == "walk":
                gha.anisotropic_costdistance(friction, points, dst_dir)
            else:
                gha.isotropic_costdistance(friction, points, dst_dir)

            # fill nodata pixels inside area of interest
            with rasterio.open(os.path.join(dst_dir, "cost.tif")) as src:
                nodata = src.nodata
                cost = src.read(1, masked=True)
                cost = gha.fill(cost, nodata=nodata)

            # population counts based on travel times
            pop = gha.population_counts(areas)
            pop_time = gha.accessibility_stats(cost, areas)

            areas = areas.join(pop.rename("population").round().astype(int))

            for mn, count in pop_time.items():
                areas = areas.join(
                    count.rename(f"population_{mn}mn").round().astype(int)
                )
                areas[f"population_{mn}mn_ratio"] = (
                    areas[f"population_{mn}mn"] / areas["population"]
                ).round(4)

            areas.to_file(os.path.join(dst_dir, "areas.gpkg"), driver="GPKG")
            areas.drop(["geometry"], axis=1).to_csv("areas.csv", index=False)
