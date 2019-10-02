import geopandas as gpd 
import pandas as pd
import os

print("Download Highways from OSM")
cmd1 = "osmium tags-filter http://download.geofabrik.de/africa/congo-democratic-republic-latest.osm.pbf w/highway -o data/osm_highways.pbf --overwrite"
os.system(cmd1)

print("Convert PBF data to GeoJson")
cmd2 = "osmium export data/osm_highways.pbf -o data/osm_highways.geojson --overwrite"
os.system(cmd2)

print("Read data in GeoPandas")
data = gpd.read_file("data/osm_highways.geojson")

print("Filter data and select features")
highway_dat = data.loc[~pd.isnull(data.highway)]
highways_map_data = gpd.GeoDataFrame(highway_dat[["highway","smoothness","surface","tracktype"]], 
                                     geometry=highway_dat["geometry"])

print("Export data")
highways_map_data.to_file("data/osm_highways.gpkg", driver="GPKG")
