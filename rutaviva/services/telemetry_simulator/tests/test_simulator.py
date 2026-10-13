import random
from typing import List

from services.telemetry_simulator.app.config import (
    LAT_MIN,
    LAT_MAX,
    LON_MIN,
    LON_MAX,
)
from services.telemetry_simulator.app.defects import (
    plan_defects,
    out_of_city_position,
)
from services.telemetry_simulator.app.vehicle import Vehiculo


def is_inside_city(lat: float, lon: float) -> bool:
    """Verifica si las coordenadas están dentro del límite urbano de NYC."""
    return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX


def test_mensaje_tiene_los_campos_del_contrato():
    """El mensaje generado contiene exactamente los campos requeridos en el contrato."""
    vehiculo = Vehiculo(
        vehicle_id="v-1",
        zone_id=1,
        latitude=40.7500,
        longitude=-73.9800,
        status="available",
    )
    payload = vehiculo.to_payload()
    expected_fields = {"vehicle_id", "zone_id", "lat", "lon", "status", "last_seen_at"}
    assert set(payload.keys()) == expected_fields
    assert payload["vehicle_id"] == "v-1"
    assert payload["status"] == "available"


def test_los_vehiculos_siempre_se_mueven_dentro_de_la_ciudad():
    """La cinemática normal de los vehículos los mantiene dentro del cuadrante urbano."""
    vehiculo = Vehiculo(
        vehicle_id="v-2",
        zone_id=10,
        latitude=40.7000,
        longitude=-74.0000,
        status="available",
    )
    # Simular 500 pasos de movimiento de 15 segundos
    for _ in range(500):
        vehiculo.tick(intervalo_segundos=15.0)
        assert is_inside_city(vehiculo.lat, vehiculo.lon)


def test_porcentajes_de_defectos_son_exactos_y_disjuntos():
    """Valida que los vehículos seleccionados para silencio y fuera de ciudad sean disjuntos y respeten los %."""
    vehicle_ids = [f"v-{i}" for i in range(1000)]
    silent_pct = 5.0
    out_of_city_pct = 3.0
    rng = random.Random(42)

    plan = plan_defects(
        vehicle_ids=vehicle_ids,
        silent_pct=silent_pct,
        out_of_city_pct=out_of_city_pct,
        rng=rng,
    )

    assert len(plan.silent_ids) == 50
    assert len(plan.out_of_city_ids) == 30
    # Deben ser conjuntos disjuntos (ningún vehículo tiene ambos defectos a la vez)
    assert not (plan.silent_ids & plan.out_of_city_ids)


def test_coordenadas_defectuosas_quedan_fuera_de_la_ciudad():
    """Las coordenadas de defecto deben ubicarse estrictamente fuera del polígono de la ciudad."""
    rng = random.Random(3)
    for _ in range(1000):
        lat, lon = out_of_city_position(rng)
        assert not is_inside_city(lat, lon)
