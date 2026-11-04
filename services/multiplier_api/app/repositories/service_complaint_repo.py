from sqlalchemy.orm import Session

from app.models.service_complaint import ServiceComplaint


def create(db: Session, complaint: ServiceComplaint) -> ServiceComplaint:
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    return complaint
