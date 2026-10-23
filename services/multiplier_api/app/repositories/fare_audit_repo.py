# app/repositories/fare_audit_repo.py
import uuid

from app.models.fare_audit import FareAudit
from sqlalchemy.orm import Session


def get_by_trip_id(db: Session, trip_id: uuid.UUID) -> FareAudit | None:
    return db.query(FareAudit).filter(FareAudit.trip_id == trip_id).first()
