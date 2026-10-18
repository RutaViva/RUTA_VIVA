# app/repositories/trip_request_repo.py
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.trip_request import TripRequest
from app.models.fare_audit import FareAudit


def create_trip_with_audit(
    db: Session, trip: TripRequest, audit: FareAudit
) -> TripRequest:
    """Inserta de forma atómica la solicitud y su auditoría inmutable."""
    db.add(trip)
    db.add(audit)
    db.commit()
    db.refresh(trip)
    return trip


def get_by_id(db: Session, trip_id: uuid.UUID) -> Optional[TripRequest]:
    return db.query(TripRequest).filter(TripRequest.trip_id == trip_id).first()


def update_status(db: Session, trip_id: uuid.UUID, new_status: str) -> Optional[TripRequest]:
    trip = get_by_id(db, trip_id)
    if trip:
        trip.status = new_status
        db.commit()
        db.refresh(trip)
    return trip
