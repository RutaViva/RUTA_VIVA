# app/services/zone_service.py
from app.models.zone import Zone
from app.repositories import zone_repo
from sqlalchemy.orm import Session


def get_zone(db: Session, zone_id: int) -> Zone | None:
    """Devuelve la zona o None si no existe en el catálogo."""
    return zone_repo.get_by_id(db, zone_id)


def get_underserved_zones(db: Session) -> list[dict]:
    """Retorna zonas desatendidas con tiempo de espera > 12 min en 3 intervalos consecutivos (RF-05, RN-08)."""
    return zone_repo.get_underserved_zones(db)

