from collections import defaultdict
from uuid import uuid4

from services.seed_cli.app import seeder


def test_generate_driver_vehicle_states_activa_un_solo_auto_por_conductor(monkeypatch):
    monkeypatch.setattr(
        seeder,
        "generate_coordinates_and_random_zone",
        lambda _zones: (40.75, -73.98, 1, "zone"),
    )
    driver_vehicle_pairs = [
        {"driver_id": driver_id, "vehicle_id": uuid4()}
        for driver_id in (uuid4(), uuid4())
        for _ in range(3)
    ]

    states = seeder.generate_driver_vehicle_states(driver_vehicle_pairs, zones_gdf=None)
    active_count_by_driver = defaultdict(int)
    vehicle_status_by_id = {
        state["vehicle_id"]: state["status"]
        for state in states
    }

    for pair in driver_vehicle_pairs:
        if vehicle_status_by_id[pair["vehicle_id"]] in {"available", "busy"}:
            active_count_by_driver[pair["driver_id"]] += 1

    assert len(states) == len(driver_vehicle_pairs)
    assert all(count == 1 for count in active_count_by_driver.values())
    assert len(active_count_by_driver) == 2
    assert all("driver_id" not in state for state in states)


def test_seeder_idempotency_ca22():
    """
    HU-02 / CA 2.2:
    Given the database populated via seed,
    When run twice,
    Then the data remains identical (referential integrity without duplicates).
    """
    import os
    from sqlalchemy import select, func
    from services.seed_cli.app.database import SessionLocal
    from services.seed_cli.app.models import Driver, Vehicle, Zone, License, Sanction, VehicleState
    from services.seed_cli.app.main import run_seeder

    session = SessionLocal()

    # 1. Primera ejecución del seeder (limpieza inicial para arrancar de estado conocido)
    run_seeder(drivers_count=15, clean_first=True)

    zones_count_1 = session.execute(select(func.count()).select_from(Zone)).scalar()
    drivers_count_1 = session.execute(select(func.count()).select_from(Driver)).scalar()
    vehicles_count_1 = session.execute(select(func.count()).select_from(Vehicle)).scalar()
    licenses_count_1 = session.execute(select(func.count()).select_from(License)).scalar()
    sanctions_count_1 = session.execute(select(func.count()).select_from(Sanction)).scalar()
    states_count_1 = session.execute(select(func.count()).select_from(VehicleState)).scalar()

    # 2. Segunda ejecución del seeder con la MISMA semilla
    run_seeder(drivers_count=15, clean_first=False)

    zones_count_2 = session.execute(select(func.count()).select_from(Zone)).scalar()
    drivers_count_2 = session.execute(select(func.count()).select_from(Driver)).scalar()
    vehicles_count_2 = session.execute(select(func.count()).select_from(Vehicle)).scalar()
    licenses_count_2 = session.execute(select(func.count()).select_from(License)).scalar()
    sanctions_count_2 = session.execute(select(func.count()).select_from(Sanction)).scalar()
    states_count_2 = session.execute(select(func.count()).select_from(VehicleState)).scalar()

    session.close()

    # Validar que los conteos son exactamente idénticos (sin registros duplicados)
    assert zones_count_1 == zones_count_2, "Las zonas no deben duplicarse"
    assert drivers_count_1 == drivers_count_2, "Los conductores no deben duplicarse"
    assert vehicles_count_1 == vehicles_count_2, "Los vehículos no deben duplicarse"
    assert licenses_count_1 == licenses_count_2, "Las licencias no deben duplicarse"
    assert sanctions_count_1 == sanctions_count_2, "Las sanciones no deben duplicarse"
    assert states_count_1 == states_count_2, "Los estados no deben duplicarse"

