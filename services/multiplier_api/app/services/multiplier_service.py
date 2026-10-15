# app/services/multiplier_service.py
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories import zone_state_repo
from app.schemas.multiplier import MultiplierResponse

logger = logging.getLogger(__name__)


def _degraded(zone_id: int, computed_at: datetime | None) -> MultiplierResponse:
    # El fallback vive SOLO aquí para que ninguna ruta se lo salte (5.4).
    return MultiplierResponse(
        zone_id=zone_id, multiplier=1.0, computed_at=computed_at, degraded=True
    )


def get_current_multiplier(db: Session, zone_id: int) -> MultiplierResponse | None:
    """Devuelve el multiplicador vigente; None si la zona no existe."""
    try:
        state = zone_state_repo.get_by_zone_id(db, zone_id)
    except SQLAlchemyError:
        logger.exception("Fallo leyendo zone_state de la zona %s", zone_id)
        return _degraded(zone_id, None)

    if state is None:
        return None

    # Dato viejo = el worker no está calculando: no se confía en él.
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    age_seconds = (now_utc - state.computed_at).total_seconds()
    if age_seconds > settings.freshness_threshold_seconds:
        logger.warning("Dato obsoleto en zona %s (%.0f s)", zone_id, age_seconds)
        return _degraded(zone_id, state.computed_at)

    return MultiplierResponse(
        zone_id=zone_id,
        multiplier=float(state.multiplier),
        computed_at=state.computed_at,
        degraded=False,
    )