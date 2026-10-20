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
