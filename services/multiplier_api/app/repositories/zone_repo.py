# app/repositories/zone_repo.py
from sqlalchemy.orm import Session

from app.models.zone import Zone

def get_by_id(db: Session, zone_id: int) -> Zone | None:
    # Lectura por clave primaria.
    return db.get(Zone, zone_id)