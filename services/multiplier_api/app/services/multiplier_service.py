# app/services/multiplier_service.py
import logging
from datetime import UTC, datetime

from app.core.config import settings
from app.repositories import zone_state_repo
from app.schemas.multiplier import MultiplierResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _degraded(zone_id: int, computed_at: datetime | None) -> MultiplierResponse:
    # El fallback vive SOLO aquí para que ninguna ruta se lo salte (5.4 / RNF-04).
    return MultiplierResponse(
        zone_id=zone_id, multiplier=1.0, computed_at=computed_at, degraded=True
    )


def get_current_multiplier(db: Session, zone_id: int) -> MultiplierResponse | None:
    """
    Devuelve el multiplicador vigente para una zona.
    Aplica política de degradación segura (RNF-04) devolviendo 1.0 (degraded=true)
    si la base de datos falla o si la telemetría calculada es más vieja que settings.freshness_threshold_seconds.
    Devuelve None si la zona no existe en el catálogo maestro.
    """
    try:
        state = zone_state_repo.get_by_zone_id(db, zone_id)
    except SQLAlchemyError:
        logger.exception("Fallo leyendo zone_state de la zona %s", zone_id)
        return _degraded(zone_id, None)

    if state is None:
        return None

    # Normalización segura de zonas horarias para evitar TypeError en sustracción
    now_utc = datetime.now(UTC)
    computed_at = state.computed_at
    if computed_at is not None and computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=UTC)

    if computed_at is None:
        return _degraded(zone_id, None)

    age_seconds = (now_utc - computed_at).total_seconds()
    if age_seconds > settings.freshness_threshold_seconds:
        logger.warning("Dato obsoleto en zona %s (%.0f s)", zone_id, age_seconds)
        return _degraded(zone_id, state.computed_at)

    return MultiplierResponse(
        zone_id=zone_id,
        multiplier=float(state.multiplier),
        computed_at=state.computed_at,
        degraded=False,
    )
