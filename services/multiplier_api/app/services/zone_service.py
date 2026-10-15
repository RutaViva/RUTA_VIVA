# app/services/zone_service.py
from sqlalchemy.orm import Session

from app.models.zone import Zone
from app.repositories import zone_repo


def get_zone(db: Session, zone_id: int) -> Zone | None:
    """Devuelve la zona o None si no existe en el catálogo."""
    return zone_repo.get_by_id(db, zone_id)