from pathlib import Path

import geopandas as gpd
from config import PROJECT_ROOT
from shapely.geometry import Point

_candidates = [
    Path("/app/data/shapefiles/taxi_zones.shp"),
    Path(__file__).resolve().parent / "data" / "shapefiles" / "taxi_zones.shp",
    PROJECT_ROOT / "services" / "seed_cli" / "app" / "data" / "shapefiles" / "taxi_zones.shp",
    Path("services/seed_cli/app/data/shapefiles/taxi_zones.shp").resolve(),
]
ZONE_SHAPEFILE = next((p for p in _candidates if p.exists()), _candidates[2])


class ZoneLocator:
    def __init__(self):
        zones = gpd.read_file(ZONE_SHAPEFILE)
        if zones.crs != "EPSG:4326":
            zones = zones.to_crs(epsg=4326)

        self._zones = zones.reset_index(drop=True)
        self._spatial_index = self._zones.sindex

    def locate(self, latitude: float, longitude: float, current_zone_id: int) -> int:
        """Devuelve la zona que contiene el punto, o conserva la última zona válida."""
        point = Point(longitude, latitude)
        matching_indexes = self._spatial_index.query(point, predicate="within")
        if len(matching_indexes) == 0:
            return current_zone_id

        matching_zone_ids = [
            int(self._zones.iloc[index]["LocationID"])
            for index in matching_indexes
        ]
        if current_zone_id in matching_zone_ids:
            return current_zone_id
        return matching_zone_ids[0]
