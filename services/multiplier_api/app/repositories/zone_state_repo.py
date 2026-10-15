# app/repositories/zone_state_repo.py
from sqlalchemy.orm import Session

from app.models.zone_state import ZoneState


def get_by_zone_id(db: Session, zone_id: int) -> ZoneState | None:
    # Lectura por clave primaria: la razón de ser del ADR-0004.
    return db.get(ZoneState, zone_id)