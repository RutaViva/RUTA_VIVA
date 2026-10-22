# services/pressure_worker/tests/test_pressure_rules.py
from datetime import UTC, datetime

from pressure_calculator import (
    apply_rain_step,
    apply_regulatory_caps,
    calculate_base_step,
)


def test_rn03_pressure_escalation_steps():
    """RN-03: Multiplicador de tarifa según índice de presión."""
    # Menor a 1.2 -> 1.0
    assert calculate_base_step(0.5) == 1.0
    assert calculate_base_step(1.19) == 1.0

    # 1.2 a 2.0 -> 1.2
    assert calculate_base_step(1.2) == 1.2
    assert calculate_base_step(1.8) == 1.2
    assert calculate_base_step(2.0) == 1.2

    # 2.0 a 3.0 -> 1.5
    assert calculate_base_step(2.01) == 1.5
    assert calculate_base_step(2.5) == 1.5
    assert calculate_base_step(3.0) == 1.5

    # Mayor a 3.0 -> 1.8
    assert calculate_base_step(3.1) == 1.8
    assert calculate_base_step(5.0) == 1.8


def test_rn04_rain_penalty_step():
    """RN-04: Si llueve más de 2 mm/h, el multiplicador sube un escalón adicional."""
    assert apply_rain_step(1.0) == 1.2
    assert apply_rain_step(1.2) == 1.5
    assert apply_rain_step(1.5) == 1.8
    assert apply_rain_step(1.8) == 2.0
    assert apply_rain_step(2.0) == 2.0  # Ya en el máximo


def test_rn05_absolute_and_night_caps():
    """RN-05: El multiplicador nunca supera 2.0 y entre 22:00 y 05:00 nunca supera 1.5."""
    # Franja diurna (14:00 NYC = 18:00 UTC)
    day_utc = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)
    assert apply_regulatory_caps(2.5, day_utc) == 2.0
    assert apply_regulatory_caps(1.8, day_utc) == 1.8

    # Franja nocturna (23:30 NYC = 03:30 UTC del día siguiente)
    night_utc = datetime(2026, 10, 16, 3, 30, tzinfo=UTC)
    assert apply_regulatory_caps(1.8, night_utc) == 1.5
    assert apply_regulatory_caps(2.0, night_utc) == 1.5
    assert apply_regulatory_caps(1.2, night_utc) == 1.2


def test_ca02_combined_case_acceptance():
    """CA-02: A las 23:30 con presión 3,5 y lluvia de 5 mm/h, el multiplicador devuelto es 1,5."""
    pressure = 3.5
    rain_mm_h = 5.0
    # 23:30 NYC -> 03:30 UTC
    current_time_utc = datetime(2026, 10, 16, 3, 30, tzinfo=UTC)

    # 1. Base step para presión 3.5 (RN-03: > 3.0 -> 1.8)
    base_mult = calculate_base_step(pressure)
    assert base_mult == 1.8

    # 2. Lluvia 5 mm/h > 2.0 mm/h (RN-04: sube un escalón 1.8 -> 2.0)
    rain_mult = apply_rain_step(base_mult) if rain_mm_h > 2.0 else base_mult
    assert rain_mult == 2.0

    # 3. Tope nocturno a las 23:30 (RN-05: máx 1.5 entre 22:00 y 05:00)
    final_mult = apply_regulatory_caps(rain_mult, current_time_utc)
    assert final_mult == 1.5


def test_rn09_exclude_suspended_and_expired_drivers_ca21():
    """
    HU-02 / CA 2.1:
    Given a driver with an expired or suspended license,
    When available supply is queried,
    Then that driver never appears in the result.
    """
    import uuid
    from datetime import date, datetime, timedelta

    from database import SessionLocal
    from models import Driver, License, Sanction, Vehicle, VehicleState
    from pressure_calculator import get_available_supply_query

    session = SessionLocal()
    today = date(2026, 10, 21)
    cutoff = datetime(2026, 10, 21, 12, 0, tzinfo=UTC) - timedelta(seconds=120)

    # 1. Driver Válido (activo, licencia vigente, sin sanción) -> DEBE APARECER
    valid_driver_id = uuid.uuid4()
    valid_veh_id = uuid.uuid4()

    # 2. Driver Suspendido (status='suspended') -> NO DEBE APARECER
    suspended_driver_id = uuid.uuid4()
    suspended_veh_id = uuid.uuid4()

    # 3. Driver con Licencia Vencida -> NO DEBE APARECER
    expired_driver_id = uuid.uuid4()
    expired_veh_id = uuid.uuid4()

    # 4. Driver con Sanción Vigente -> NO DEBE APARECER
    sanctioned_driver_id = uuid.uuid4()
    sanctioned_veh_id = uuid.uuid4()

    try:
        # Insertar conductores
        session.add_all([
            Driver(driver_id=valid_driver_id, full_name="Valid Driver", status="active"),
            Driver(driver_id=suspended_driver_id, full_name="Suspended Driver", status="suspended"),
            Driver(driver_id=expired_driver_id, full_name="Expired License Driver", status="active"),
            Driver(driver_id=sanctioned_driver_id, full_name="Sanctioned Driver", status="active"),
        ])
        # Insertar vehículos
        session.add_all([
            Vehicle(vehicle_id=valid_veh_id, driver_id=valid_driver_id, plate=f"VAL-{valid_veh_id.hex[:4].upper()}"),
            Vehicle(vehicle_id=suspended_veh_id, driver_id=suspended_driver_id, plate=f"SUS-{suspended_veh_id.hex[:4].upper()}"),
            Vehicle(vehicle_id=expired_veh_id, driver_id=expired_driver_id, plate=f"EXP-{expired_veh_id.hex[:4].upper()}"),
            Vehicle(vehicle_id=sanctioned_veh_id, driver_id=sanctioned_driver_id, plate=f"SNC-{sanctioned_veh_id.hex[:4].upper()}"),
        ])
        # Insertar licencias
        session.add_all([
            License(license_id=uuid.uuid4(), driver_id=valid_driver_id, expires_on=today + timedelta(days=100)),
            License(license_id=uuid.uuid4(), driver_id=suspended_driver_id, expires_on=today + timedelta(days=100)),
            License(license_id=uuid.uuid4(), driver_id=expired_driver_id, expires_on=today - timedelta(days=5)),
            License(license_id=uuid.uuid4(), driver_id=sanctioned_driver_id, expires_on=today + timedelta(days=100)),
        ])
        # Sanción para sanctioned_driver
        session.add(
            Sanction(
                sanction_id=uuid.uuid4(),
                driver_id=sanctioned_driver_id,
                starts_on=today - timedelta(days=2),
                ends_on=today + timedelta(days=5),
            )
        )
        # Estados disponibles
        now_ts = datetime(2026, 10, 21, 11, 59, tzinfo=UTC)
        session.add_all([
            VehicleState(vehicle_id=valid_veh_id, zone_id=161, latitude=40.75, longitude=-73.98, status="available", last_seen_at=now_ts),
            VehicleState(vehicle_id=suspended_veh_id, zone_id=161, latitude=40.75, longitude=-73.98, status="available", last_seen_at=now_ts),
            VehicleState(vehicle_id=expired_veh_id, zone_id=161, latitude=40.75, longitude=-73.98, status="available", last_seen_at=now_ts),
            VehicleState(vehicle_id=sanctioned_veh_id, zone_id=161, latitude=40.75, longitude=-73.98, status="available", last_seen_at=now_ts),
        ])
        session.commit()

        # Ejecutar la consulta de oferta
        query = get_available_supply_query(today=today, cutoff_telemetry=cutoff)
        results = session.execute(query).all()
        returned_driver_ids = {row.driver_id for row in results}

        # Comprobar aserciones de aceptación RN-09:
        assert valid_driver_id in returned_driver_ids, "El conductor válido debe figurar en la oferta disponible"
        assert suspended_driver_id not in returned_driver_ids, "El conductor suspendido NUNCA debe aparecer en la oferta (RN-09)"
        assert expired_driver_id not in returned_driver_ids, "El conductor con licencia vencida NUNCA debe aparecer en la oferta (RN-09)"
        assert sanctioned_driver_id not in returned_driver_ids, "El conductor con sanción activa NUNCA debe aparecer en la oferta (RN-09)"

    finally:
        session.rollback()
        for v_id in [valid_veh_id, suspended_veh_id, expired_veh_id, sanctioned_veh_id]:
            session.query(VehicleState).filter(VehicleState.vehicle_id == v_id).delete()
            session.query(Vehicle).filter(Vehicle.vehicle_id == v_id).delete()
        for d_id in [valid_driver_id, suspended_driver_id, expired_driver_id, sanctioned_driver_id]:
            session.query(Sanction).filter(Sanction.driver_id == d_id).delete()
            session.query(License).filter(License.driver_id == d_id).delete()
            session.query(Driver).filter(Driver.driver_id == d_id).delete()
        session.commit()
        session.close()

