import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_complaint import ServiceComplaint
from app.repositories import service_complaint_repo, trip_request_repo
from app.schemas.service_complaint import ComplaintCategory


def create_complaint(
    db: Session,
    trip_id: uuid.UUID,
    category: ComplaintCategory,
) -> Optional[ServiceComplaint]:
    if trip_request_repo.get_by_id(db, trip_id) is None:
        return None

    complaint = ServiceComplaint(
        trip_id=trip_id,
        category=category,
    )
    return service_complaint_repo.create(db, complaint)
