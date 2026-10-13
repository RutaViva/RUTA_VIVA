"""
Módulo encargado de la simulación probabilística y generación de diccionarios
de datos coherentes listos para inserción masiva.
"""
import os
import random
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
import pandas as pd
from faker import Faker
import geopandas as gpd
from shapely.geometry import Point
import numpy as np

# Hay que tener una variable de entorno que defina la seed
SEED = os.getenv("SEED")
NP_SEED = os.getenv("NP_SEED")

# Inicializamos Faker con la localización en inglés de Estados Unidos.
fake = Faker("en_US")

# Resolver las rutas desde este archivo, no desde el directorio de ejecución.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CSV_PATH = os.path.join(DATA_DIR, "csv", "taxi_zone_lookup.csv")
SHAPEFILE_PATH = os.path.join(DATA_DIR, "shapefiles", "taxi_zones.shp")
GEOJSON_PATH = os.path.join(DATA_DIR, "geojson", "sync_taxi_zones.geojson")

# Cargar el CSV de zonas de taxi para obtener los LocationID
df = pd.read_csv(CSV_PATH)
zone_ids = df["LocationID"].tolist()

# Determinamos si hay o no una seed.
if SEED is not None:
    SEED = int(SEED)
# Valor default para reproducibilidad de resultados.
elif SEED is None:
    SEED = 1230821048148
    NP_SEED = 45

random.seed(SEED)
Faker.seed(SEED)
np.random.seed(NP_SEED)

# Coordenadas aproximadas del área metropolitana de Nueva York
LAT_MIN, LAT_MAX = 40.4900, 40.9200
LON_MIN, LON_MAX = -74.2700, -73.6800

DRIVER_STATUSES = ["active", "inactive", "suspended"]
VEHICLE_STATUSES = ["available", "busy", "offline", "maintenance"]


def uuid_from_random() -> uuid.UUID:
    """Genera UUID reproducibles usando el estado del módulo random."""
    return uuid.UUID(int=random.getrandbits(128))


def generate_zones() -> List[Dict[str, Any]]:
    return [
        {
            "zone_id": int(row["LocationID"]),
            "borough": row["Borough"],
            "zone_name": row["Zone"],
        }
        for row in df.to_dict(orient="records")
    ]


def generate_drivers(count: int) -> List[Dict[str, Any]]:
    return [
        {
            "driver_id": uuid_from_random(),
            "full_name": fake.name(),
        }
        
        for _ in range(count)
    ] 


def generate_vehicles(
    driver_ids: List[uuid.UUID],
    min_vehicles_per_driver: int = 0,
    max_vehicles_per_driver: int = 2,
) -> List[Dict[str, Any]]:
    """
    Genera vehículos asignando entre min y max vehículos a cada conductor (Relación 1 a N).
    """
    vehicles = []
    used_plates = set()

    for d_id in driver_ids:
        num_vehicles = random.randint(min_vehicles_per_driver, max_vehicles_per_driver)
        for _ in range(num_vehicles):
            # Generar placa única.
            while True:
                plate = f"{fake.bothify(text='???').upper()}-{fake.bothify(text='####')}"
                if plate not in used_plates:
                    used_plates.add(plate)
                    break

            vehicles.append({
                "vehicle_id": uuid_from_random(),
                "driver_id": d_id,
                "plate": plate,
            })
    return vehicles


def generate_licenses(driver_ids: List[uuid.UUID]) -> List[Dict[str, Any]]:
    today = date.today()
    licenses = []
    for d_id in driver_ids:
        # 85% de licencias vigentes (incluye hoy), 15% vencidas.
        if random.random() < 0.85:
            expires_on = fake.date_between(
                start_date=today,
                end_date=today + timedelta(days=730),
            )
        else:
            expires_on = fake.date_between(
                start_date=today - timedelta(days=365),
                end_date=today - timedelta(days=1),
            )

        licenses.append({
            "license_id": uuid_from_random(),
            "driver_id": d_id,
            "expires_on": expires_on,
        })
    return licenses


def generate_sanctions(
    driver_ids: List[uuid.UUID],
    probability: float = 0.2,
    max_sanctions: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not 0 <= probability <= 1:
        raise ValueError("probability debe estar entre 0 y 1.")
    if max_sanctions is not None and max_sanctions < 0:
        raise ValueError("max_sanctions no puede ser negativo.")

    today = date.today()
    eligible_driver_ids = [
        d_id for d_id in driver_ids if random.random() < probability
    ]
    if max_sanctions is not None and len(eligible_driver_ids) > max_sanctions:
        eligible_driver_ids = random.sample(eligible_driver_ids, max_sanctions)

    sanctions = []
    for d_id in eligible_driver_ids:
        duration_days = random.randint(7, 90)
        if random.random() < 0.60:
            # La sanción cubre hoy, inclusive.
            starts_on = today - timedelta(days=random.randint(0, duration_days))
            ends_on = starts_on + timedelta(days=duration_days)
        else:
            # La sanción terminó antes de hoy.
            ends_on = today - timedelta(days=random.randint(1, 90))
            starts_on = ends_on - timedelta(days=duration_days)

        sanctions.append({
            "sanction_id": uuid_from_random(),
            "driver_id": d_id,
            "starts_on": starts_on,
            "ends_on": ends_on,
        })
    return sanctions


def compute_driver_status(driver_id, licenses_by_driver, sanctions_by_driver) -> str:
    today = date.today()
    driver_licenses = licenses_by_driver.get(driver_id, [])
    if not driver_licenses:
        raise ValueError(f"El driver {driver_id} no tiene una licencia asociada.")

    has_current_sanction = any(
        sanction["starts_on"] <= today <= sanction["ends_on"]
        for sanction in sanctions_by_driver.get(driver_id, [])
    )
    if has_current_sanction:
        return "suspended"       # ← antes: "SUSPENDED"

    license_is_expired = all(
        license_data["expires_on"] < today
        for license_data in driver_licenses
    )
    if license_is_expired:
        return "inactive"        # ← antes: "INACTIVE"
    return "active"              # ← antes: "ACTIVE"

def apply_driver_status(
    drivers: List[Dict[str, Any]],
    licenses: List[Dict[str, Any]],
    sanctions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    licenses_by_driver: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    sanctions_by_driver: Dict[uuid.UUID, List[Dict[str, Any]]] = {}

    for license_data in licenses:
        licenses_by_driver.setdefault(license_data["driver_id"], []).append(license_data)
    for sanction in sanctions:
        sanctions_by_driver.setdefault(sanction["driver_id"], []).append(sanction)

    for driver in drivers:
        driver["status"] = compute_driver_status(driver["driver_id"], licenses_by_driver, sanctions_by_driver)
    return drivers

def compute_vehicle_status() -> str:
    return random.choices(
        ["available", "busy", "offline", "maintenance"],   # ← minúsculas
        weights=[50, 30, 10, 10],
        k=1,
    )[0]

#cargar la carpeta con el .shp
zones_gdf = gpd.read_file(SHAPEFILE_PATH)

#convertir y guardar a GeoJSON
zones_gdf.to_file(GEOJSON_PATH, driver="GeoJSON")
if zones_gdf.crs != "EPSG:4326":
    zones_gdf = zones_gdf.to_crs(epsg=4326)

def generate_coordinates_and_random_zone(zones_gdf):
    # 1. Seleccionar una zona aleatoria del dataset
    zona = zones_gdf.sample(1).iloc[0]
    poligono = zona['geometry']
    
    # 2. Obtenemos el bounding box exacto de ESA zona (no de todo NYC)
    min_lon, min_lat, max_lon, max_lat = poligono.bounds
    
    # 3. Generamos puntos dentro de ese recuadro pequeño hasta acertar en el polígono
    while True:
        lat = round(random.uniform(min_lat, max_lat), 6)
        lon = round(random.uniform(min_lon, max_lon), 6)
        
        if poligono.contains(Point(lon, lat)):
            return lat, lon, zona['LocationID'], zona['zone']


def generate_vehicle_states(
    vehicle_ids: List[uuid.UUID],
) -> List[Dict[str, Any]]:
    states = []
    today_midnight = datetime.combine(date.today(), datetime.min.time())

    for v_id in vehicle_ids:
        latitude, longitude, zone_id, _ = generate_coordinates_and_random_zone(zones_gdf)

        states.append({
            "vehicle_id": v_id,
            "zone_id": zone_id,
            "latitude": latitude,
            "longitude": longitude,
            "status": compute_vehicle_status(),
            "last_seen_at": today_midnight - timedelta(seconds=random.randint(5, 3600)),
        })
    return states


import random
from datetime import datetime, timezone

def generate_driver_vehicle_states(driver_vehicle_pairs, zones_gdf):
    """
    driver_vehicle_pairs: Lista de tuplas o diccionarios con (driver_id, vehicle_id)
    Garantiza que si un conductor tiene múltiples vehículos, solo uno esté activo.
    """
    # 1. Agrupar vehículos por conductor
    driver_vehicles = {}
    for pair in driver_vehicle_pairs:
        d_id = pair['driver_id']
        v_id = pair['vehicle_id']
        driver_vehicles.setdefault(d_id, []).append(v_id)

    vehicle_states = []

    # 2. Asignar estados respetando las reglas de negocio
    for driver_id, vehicles in driver_vehicles.items():
        # Mezclar la lista para que el vehículo activo sea aleatorio
        random.shuffle(vehicles)
        
        # El PRIMER vehículo del conductor será el ACTIVO
        active_vehicle_id = vehicles[0]
        lat, lon, zone_id, _ = generate_coordinates_and_random_zone(zones_gdf)
        
        vehicle_states.append({
            "driver_id": driver_id,
            "vehicle_id": active_vehicle_id,
            "zone_id": zone_id,
            "latitude": lat,
            "longitude": lon,
            "status": random.choice(["available", "busy"]), # Solo el activo está Available/Busy
            "last_seen_at": datetime.now(timezone.utc)
        })

        # Los demás vehículos del mismo conductor serán INACTIVOS (Offline o Mantenimiento)
        for inactive_vehicle_id in vehicles[1:]:
            # También se les genera o asigna su última ubicación conocida (ej. base o taller)
            inact_lat, inact_lon, inact_zone_id, _ = generate_coordinates_and_random_zone(zones_gdf)
            
            vehicle_states.append({
                "driver_id": driver_id,
                "vehicle_id": inactive_vehicle_id,
                "zone_id": inact_zone_id,
                "latitude": inact_lat,
                "longitude": inact_lon,
                "status": random.choice(["offline", "maintenance"]), # Nunca AVAILABLE/BUSY
                "last_seen_at": datetime.now(timezone.utc)
            })

    return vehicle_states


def validate_consistency(
    drivers: List[Dict[str, Any]],
    licenses: List[Dict[str, Any]],
    sanctions: List[Dict[str, Any]],
    vehicles: List[Dict[str, Any]],
    vehicle_states: List[Dict[str, Any]],
) -> None:
    #Traer los ids de conductores, sanciones, licencias y estados de vehiculos para validacion
    licenses_by_driver: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    sanctions_by_driver: Dict[uuid.UUID, List[Dict[str, Any]]] = {}
    drivers_by_id = {driver["driver_id"]: driver for driver in drivers}
    states_by_vehicle_id = {
        state["vehicle_id"]: state for state in vehicle_states
    }

    for license_data in licenses:
        licenses_by_driver.setdefault(license_data["driver_id"], []).append(license_data)
    for sanction in sanctions:
        sanctions_by_driver.setdefault(sanction["driver_id"], []).append(sanction)

    #Validar coherencia del conductor
    for driver in drivers:
        #Revizamos que tenga licencia 
        if not licenses_by_driver.get(driver["driver_id"]):
            raise AssertionError(
                f"Driver {driver['driver_id']}: no tiene una licencia asociada."
            )
        #Traemos el estado "esperado" con la funcion que genera el estado
        expected_status = compute_driver_status(
            driver["driver_id"],
            licenses_by_driver,
            sanctions_by_driver,
        )
        #Si es diferente entonces salta un error
        if driver.get("status") != expected_status:
            raise AssertionError(
                f"Driver {driver['driver_id']}: status {driver.get('status')!r}; "
                f"se esperaba {expected_status!r} según licencia y sanciones."
            )

    #Validar existencia de relaciones y validez de estados de vehículos
    for vehicle in vehicles:
        vehicle_id = vehicle["vehicle_id"]
        driver_id = vehicle["driver_id"]
        #Revizamos que el conductor asociado al auto exista en la lista de conductores
        if driver_id not in drivers_by_id:
            raise AssertionError(
                f"Vehículo {vehicle_id}: driver_id {driver_id} no existe."
            )
         
        if vehicle_id not in states_by_vehicle_id:
            raise AssertionError(f"Vehículo {vehicle_id}: no tiene estado asociado.")

        vehicle_status = states_by_vehicle_id[vehicle_id]["status"]
        if vehicle_status not in VEHICLE_STATUSES:
            raise AssertionError(
                f"Vehículo {vehicle_id}: el status {vehicle_status!r} no es un estado válido.")


if __name__ == "__main__":
    # Ejemplo de uso
    num_drivers = 5
    drivers = generate_drivers(num_drivers)
    licenses = generate_licenses([d["driver_id"] for d in drivers])
    sanctions = generate_sanctions([d["driver_id"] for d in drivers], probability=0.3)
    vehicles = generate_vehicles([d["driver_id"] for d in drivers], min_vehicles_per_driver=1, max_vehicles_per_driver=2)
    vehicle_states = generate_driver_vehicle_states([{"driver_id": v["driver_id"], "vehicle_id": v["vehicle_id"]} for v in vehicles],zones_gdf)

    # Aplicar el estado a los conductores
    drivers_with_status = apply_driver_status(drivers, licenses, sanctions)

    # Validar consistencia de los datos generados
    validate_consistency(drivers_with_status, licenses, sanctions, vehicles, vehicle_states)

    for i in licenses:
        print(i)

    for i in sanctions:
        print(i)

    for i in drivers_with_status:
        print(i)

    for i in vehicles:
        print(i)

    for i in vehicle_states:
        print(i)

    print("Datos generados y validados correctamente.")