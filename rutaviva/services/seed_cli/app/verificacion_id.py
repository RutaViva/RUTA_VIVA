from pathlib import Path

import os

import pandas as pd, geopandas as gpd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "seed_cli", "app", "data")

df_csv = pd.read_csv(os.path.join(DATA_DIR, "csv", "taxi_zone_lookup.csv"))
gdf_shp = gpd.read_file(os.path.join(DATA_DIR, "shapefiles", "taxi_zones.shp"))

ids_csv = set(df_csv["LocationID"].astype(int))
ids_shp = set(gdf_shp["LocationID"].astype(int))

print("Solo en shapefile:", ids_shp - ids_csv)
print("Solo en CSV:", ids_csv - ids_shp)