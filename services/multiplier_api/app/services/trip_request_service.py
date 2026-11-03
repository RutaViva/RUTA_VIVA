# app/services/trip_request_service.py
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.fare_audit import FareAudit
from app.models.tariff_rule_version import TariffRuleVersion
from app.models.trip_request import TripRequest
from app.models.weather_current import WeatherCurrent
from app.models.zone_state import ZoneState
from app.repositories import trip_request_repo, zone_repo
from app.schemas.trip_request import TripResponse
from app.services import multiplier_service
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def create_trip_request(
    db: Session, zone_id: int, base_fare: float
) -> TripResponse | None:
    """
    Registra una solicitud de viaje y congela atómicamente la tarifa
    con el multiplicador vigente al momento de la solicitud (RN-07, RN-12).

    Garantiza:
    - Validación de existencia de la zona de origen (1-265).
    - Obtención del multiplicador dinámico actual o degradación segura 1.0 (RNF-04).
    - Cálculo matemático preciso con Decimal para evitar imprecisiones de coma flotante.
    - Aseguramiento de la clave foránea de versión de regla tarifaria (rule_version_id=1).
    - Creación simultánea en una sola transacción atómica de trip_request y fare_audit.
    """
    # 1. Validar existencia de la zona en el catálogo maestro
    zone = zone_repo.get_by_id(db, zone_id)
    if zone is None:
        return None

    now_utc = datetime.now(UTC)

    # 2. Obtener multiplicador vigente y estado (con degradación segura RNF-04)
    mult_resp = multiplier_service.get_current_multiplier(db, zone_id)
    multiplier_val = mult_resp.multiplier if mult_resp else 1.0
    degraded = mult_resp.degraded if mult_resp else True

    # 3. Leer presión de zone_state de forma segura
    zone_state = db.query(ZoneState).filter(ZoneState.zone_id == zone_id).first()
    pressure_index = (
        float(zone_state.pressure_index)
        if zone_state and zone_state.pressure_index is not None
        else 1.0
    )

    # 4. Leer clima más reciente de weather_current
    latest_weather = (
        db.query(WeatherCurrent)
        .order_by(WeatherCurrent.valid_hour.desc())
        .first()
    )
    rain_mm_h = (
        float(latest_weather.rain_mm_h)
        if latest_weather and latest_weather.rain_mm_h is not None
        else 0.0
    )

    # 5. Asegurar existencia de regla tarifaria versión 1 (RN-12)
    rule_ver = db.query(TariffRuleVersion).filter(TariffRuleVersion.rule_version_id == 1).first()
    if rule_ver is None:
        rule_ver = TariffRuleVersion(
            rule_version_id=1,
            valid_from=now_utc.date(),
            rules={
                "base_fare": 1.50,
                "per_km": 0.35,
                "per_minute": 0.15,
                "min_multiplier": 1.0,
                "max_multiplier": 2.0,
            },
        )
        db.add(rule_ver)
        db.flush()

    # 6. Calcular tarifa final cobrada (base * multiplicador) con precisión Decimal
    base_decimal = Decimal(str(round(base_fare, 2)))
    mult_decimal = Decimal(str(round(multiplier_val, 2)))
    charged_decimal = round(base_decimal * mult_decimal, 2)

    trip_id = uuid.uuid4()
    trip = TripRequest(
        trip_id=trip_id,
        zone_id=zone_id,
        requested_at=now_utc,
        status="created",
    )

    audit = FareAudit(
        trip_id=trip_id,
        base_fare=base_decimal,
        multiplier=mult_decimal,
        charged_fare=charged_decimal,
        pressure_index=pressure_index,
        rain_mm_h=rain_mm_h,
        rule_version_id=1,
    )

    # 7. Persistir atómicamente en PostgreSQL
    trip_request_repo.create_trip_with_audit(db, trip, audit)
    logger.info(
        "Viaje %s creado en zona %d. Multiplicador: %.2f (degradado=%s), Cobrado: $%.2f",
        trip_id,
        zone_id,
        multiplier_val,
        degraded,
        float(charged_decimal),
    )

    return TripResponse(
        trip_id=trip_id,
        zone_id=zone_id,
        requested_at=now_utc,
        status="created",
        base_fare=float(base_decimal),
        multiplier=float(mult_decimal),
        charged_fare=float(charged_decimal),
        degraded=degraded,
    )


def update_trip_status(
    db: Session, trip_id: uuid.UUID, new_status: str
) -> TripRequest | None:
    return trip_request_repo.update_status(db, trip_id, new_status)
