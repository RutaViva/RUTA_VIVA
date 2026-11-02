import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.service_complaint import (
    ServiceComplaintCreateRequest,
    ServiceComplaintResponse,
)
from app.services import service_complaint_service

router = APIRouter(prefix="/trip-requests", tags=["service-complaints"])


@router.post(
    "/{trip_id}/complaints",
    response_model=ServiceComplaintResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_complaint(
    request: ServiceComplaintCreateRequest,
    trip_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
) -> ServiceComplaintResponse:
    complaint = service_complaint_service.create_complaint(
        db,
        trip_id=trip_id,
        category=request.category,
    )
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud de viaje no encontrada.",
        )
    return complaint
