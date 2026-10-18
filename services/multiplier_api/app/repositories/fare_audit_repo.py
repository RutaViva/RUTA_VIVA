# app/repositories/fare_audit_repo.py
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.fare_audit import FareAudit


def get_by_trip_id(db: Session, trip_id: uuid.UUID) -> Optional[FareAudit]:
    return db.query(FareAudit).filter(FareAudit.trip_id == trip_id).first()
