"""Shared loaders for the TLC zone catalog and its geographic boundaries."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CATALOG_PATH = DATA_DIR / "csv" / "taxi_zone_lookup.csv"
DEFAULT_SHAPEFILE_PATH = DATA_DIR / "shapefiles" / "taxi_zones.shp"


def load_zone_catalog(path: str | Path | None = None) -> pd.DataFrame:
    catalog = pd.read_csv(path or DEFAULT_CATALOG_PATH)
    required = {"LocationID", "Borough", "Zone"}
    missing = required - set(catalog.columns)
    if missing:
        raise ValueError(
            "El catálogo de zonas no tiene las columnas requeridas: "
            + ", ".join(sorted(missing))
        )
    if catalog["LocationID"].duplicated().any():
        raise ValueError("El catálogo de zonas contiene LocationID duplicados.")
    return catalog


def load_zones_gdf(
    path: str | Path | None = None, target_crs: int | None = 4326
) -> gpd.GeoDataFrame:
    zones = gpd.read_file(path or DEFAULT_SHAPEFILE_PATH)
    required = {"LocationID", "borough", "zone", "geometry"}
    missing = required - set(zones.columns)
    if missing:
        raise ValueError(
            "El shapefile de zonas no tiene las columnas requeridas: "
            + ", ".join(sorted(missing))
        )
    if zones.crs is None:
        raise ValueError("El shapefile de zonas no declara su sistema de coordenadas.")
    if zones["LocationID"].duplicated().any():
        raise ValueError("El shapefile de zonas contiene LocationID duplicados.")
    if zones.geometry.isna().any() or zones.geometry.is_empty.any():
        raise ValueError("El shapefile de zonas contiene geometrías vacías.")
    if target_crs is not None and zones.crs.to_epsg() != target_crs:
        zones = zones.to_crs(epsg=target_crs)
    return zones
