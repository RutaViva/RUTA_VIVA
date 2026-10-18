# app/routers/trip_request.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.trip_request import (
    TripCreateRequest,
    TripResponse,
    TripStatusUpdateRequest,
)
from app.services import trip_request_service

router = APIRouter(prefix="/trip-requests", tags=["trip-requests"])


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
def create_trip(
    request: TripCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Crea una solicitud de viaje en una zona (F5).
    Aplica y congela el multiplicador vigente en el instante de la solicitud (RN-07)
    y genera la traza inmutable en fare_audit (RN-12).
    """
    result = trip_request_service.create_trip_request(
        db, zone_id=request.zone_id, base_fare=request.base_fare
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Zona {request.zone_id} inexistente en el catálogo maestro.",
        )
    return result


@router.post("/{trip_id}/assign", status_code=status.HTTP_200_OK)
def assign_trip(
    trip_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
):
    """Marca la solicitud como asignada a un vehículo."""
    trip = trip_request_service.update_trip_status(db, trip_id, "assigned")
    if trip is None:
        raise HTTPException(status_code=404, detail="Solicitud de viaje no encontrada")
    return {"trip_id": trip.trip_id, "status": trip.status}


@router.post("/{trip_id}/cancel", status_code=status.HTTP_200_OK)
def cancel_trip(
    trip_id: uuid.UUID = Path(...),
    db: Session = Depends(get_db),
):
    """Cancela una solicitud de viaje."""
    trip = trip_request_service.update_trip_status(db, trip_id, "cancelled")
    if trip is None:
        raise HTTPException(status_code=404, detail="Solicitud de viaje no encontrada")
    return {"trip_id": trip.trip_id, "status": trip.status}
