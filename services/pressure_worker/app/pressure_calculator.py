# services/pressure_worker/app/pressure_calculator.py
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from models import (
    Driver,
    License,
    Sanction,
    SpecialEvent,
    TripRequest,
    Vehicle,
    VehicleState,
    WeatherCurrent,
    Zone,
    ZoneState,
    ZoneStateHistory,
)
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from worker_config import settings

logger = logging.getLogger(__name__)


def calculate_base_step(pressure_index: float) -> float:
    """Escalonamiento base según el índice de presión (RN-03)."""
    if pressure_index < 1.2:
        return 1.0
    elif pressure_index <= 2.0:
        return 1.2
    elif pressure_index <= 3.0:
        return 1.5
    else:
        return 1.8


def apply_rain_step(multiplier: float) -> float:
    """Sube un escalón adicional si llueve más de 2 mm/h (RN-04)."""
    steps = [1.0, 1.2, 1.5, 1.8, 2.0]
    try:
        idx = steps.index(round(multiplier, 2))
        return steps[min(idx + 1, len(steps) - 1)]
    except ValueError:
        if multiplier < 1.2:
            return 1.2
        elif multiplier < 1.5:
            return 1.5
        elif multiplier < 1.8:
            return 1.8
        else:
            return 2.0


def apply_regulatory_caps(multiplier: float, current_time_utc: datetime) -> float:
    """
    Tope regulatorio (RN-05):
    - El multiplicador nunca supera 2.0.
    - Entre 22:00 y 05:00 hora local (asumido UTC-4 / UTC-5 NYC), nunca supera 1.5.
    """
    # NYC es UTC-4 (EDT) o UTC-5 (EST); usamos UTC-4 como referencia estándar de verano
    nyc_hour = (current_time_utc.hour - 4) % 24
    is_night = nyc_hour >= 22 or nyc_hour < 5

    capped = min(multiplier, settings.max_multiplier)
    if is_night:
        capped = min(capped, settings.night_max_multiplier)
    return round(capped, 2)


def get_available_supply_query(today, cutoff_telemetry):
    """
    Construye la consulta de oferta disponible aplicando RN-09 y RN-10:
    - Estado de vehículo 'available'
    - Telemetría fresca (last_seen_at >= cutoff_telemetry, RN-10)
    - Conductor no suspendido (Driver.status != 'suspended', RN-09, CA-06)
    - Licencia vigente (License.expires_on >= today, RN-09)
    - Sin sanción activa hoy (Sanction.sanction_id IS NULL, RN-09)
    """
    return (
        select(VehicleState.zone_id, VehicleState.vehicle_id, Driver.driver_id)
        .join(Vehicle, VehicleState.vehicle_id == Vehicle.vehicle_id)
        .join(Driver, Vehicle.driver_id == Driver.driver_id)
        .join(License, Driver.driver_id == License.driver_id)
        .outerjoin(
            Sanction,
            and_(
                Driver.driver_id == Sanction.driver_id,
                Sanction.starts_on <= today,
                Sanction.ends_on >= today,
            ),
        )
        .where(
            and_(
                VehicleState.status == "available",
                VehicleState.last_seen_at >= cutoff_telemetry,
                VehicleState.zone_id.isnot(None),
                Driver.status != "suspended",
                License.expires_on >= today,
                Sanction.sanction_id.is_(None),
            )
        )
    )


def compute_zone_metrics(session: Session, now_utc: datetime) -> None:
    """
    Calcula la oferta, demanda y multiplicadores para todas las zonas
    y actualiza zone_state y zone_state_history de forma atómica.
    """
    today = now_utc.date()
    cutoff_telemetry = now_utc - timedelta(seconds=settings.offline_threshold_seconds)
    cutoff_requests = now_utc - timedelta(minutes=10)

    # 1. Obtener precipitación pluvial actual (F3 / weather_current)
    latest_weather = session.execute(
        select(WeatherCurrent)
        .order_by(WeatherCurrent.valid_hour.desc())
        .limit(1)
    ).scalar_one_or_none()
    current_rain_mm_h = latest_weather.rain_mm_h if latest_weather else 0.0

    # 2. Obtener emergencias activas por zona (RN-06)
    active_emergencies = set(
        session.scalars(
            select(SpecialEvent.zone_id).where(
                and_(
                    SpecialEvent.is_emergency.is_(True),
                    SpecialEvent.starts_at <= now_utc,
                    SpecialEvent.ends_at >= now_utc,
                )
            )
        ).all()
    )

    # 3. Contar vehículos libres válidos por zona (RN-09, RN-10)
    supply_subq = get_available_supply_query(today, cutoff_telemetry).subquery()
    free_vehicles_query = (
        select(supply_subq.c.zone_id, func.count(supply_subq.c.vehicle_id).label("free_count"))
        .group_by(supply_subq.c.zone_id)
    )
    free_counts = dict(session.execute(free_vehicles_query).all())

    # 4. Contar solicitudes recientes en los últimos 10 minutos (RN-02)
    requests_query = (
        select(TripRequest.zone_id, func.count(TripRequest.trip_id).label("req_count"))
        .where(TripRequest.requested_at >= cutoff_requests)
        .group_by(TripRequest.zone_id)
    )
    request_counts = dict(session.execute(requests_query).all())

    # 5. Iterar por todas las zonas de NYC (1 a 265)
    all_zones = session.scalars(select(Zone.zone_id)).all()

    for zone_id in all_zones:
        free_veh = free_counts.get(zone_id, 0)
        req_10m = request_counts.get(zone_id, 0)

        # Cálculo de presión (RN-02)
        if free_veh > 0:
            pressure = float(req_10m) / float(free_veh)
        else:
            pressure = 4.0 if req_10m > 0 else 1.0

        pressure_index = round(pressure, 3)

        # Aplicación de reglas
        mult = calculate_base_step(pressure_index)

        # RN-04: Lluvia
        if current_rain_mm_h > settings.rain_threshold_mm_h:
            mult = apply_rain_step(mult)

        # RN-05: Topes regulatorios y nocturnos
        mult = apply_regulatory_caps(mult, now_utc)

        # RN-06 / CA-03: Emergencia congela obligatoriamente a 1.0
        if zone_id in active_emergencies:
            mult = 1.0

        mult_decimal = Decimal(str(round(mult, 2)))

        # Estimar tiempo de espera en minutos (RN-08): base 3.0 min * presión
        estimated_wait = round(max(2.0, 3.0 * pressure_index), 1)

        # Upsert atómico en zone_state
        stmt_state = pg_insert(ZoneState).values(
            zone_id=zone_id,
            computed_at=now_utc,
            pressure_index=pressure_index,
            multiplier=mult_decimal,
            free_vehicles=free_veh,
            requests_last_10min=req_10m,
        ).on_conflict_do_update(
            index_elements=[ZoneState.zone_id],
            set_={
                "computed_at": now_utc,
                "pressure_index": pressure_index,
                "multiplier": mult_decimal,
                "free_vehicles": free_veh,
                "requests_last_10min": req_10m,
            },
        )
        session.execute(stmt_state)

        # Inserción en zone_state_history
        stmt_history = pg_insert(ZoneStateHistory).values(
            zone_id=zone_id,
            interval_start=now_utc,
            requests=req_10m,
            free_vehicles=free_veh,
            pressure_index=pressure_index,
            multiplier=mult_decimal,
            estimated_wait_minutes=estimated_wait,
        ).on_conflict_do_nothing()
        session.execute(stmt_history)

    logger.info(
        "Cálculo de presión completado para %d zonas (Lluvia: %.1f mm/h, Emergencias: %d).",
        len(all_zones),
        current_rain_mm_h,
        len(active_emergencies),
    )
