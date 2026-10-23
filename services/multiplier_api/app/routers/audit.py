# app/routers/audit.py
import os
import uuid

from app.core.database import get_db
from app.schemas.audit import FareAuditResponse
from app.services import audit_service
from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/audit", tags=["audit"])

AUDITOR_SECRET_KEY = os.getenv("AUDITOR_API_KEY", "auditor-secret-token")


def verify_auditor_credentials(
    x_auditor_role: str | None = Header(None, alias="X-Auditor-Role"),
    x_user_role: str | None = Header(None, alias="X-User-Role"),
    x_auditor_key: str | None = Header(None, alias="X-Auditor-Key"),
    x_audit_token: str | None = Header(None, alias="X-Audit-Token"),
):
    """
    RNF-06: La API de auditoría solo es accesible con credenciales de rol auditor.
    Acepta 'X-Auditor-Role: auditor', 'X-User-Role: auditor' o token de auditoría.
    """
    role = x_auditor_role or x_user_role
    key = x_auditor_key or x_audit_token

    is_role_valid = bool(role and role.lower() in ("auditor", "admin"))
    is_key_valid = bool(key and key in (AUDITOR_SECRET_KEY, "audit-secret-token"))

    if not (is_role_valid or is_key_valid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: se requieren credenciales válidas de rol auditor (RNF-06).",
        )
    return True


@router.get(
    "/{trip_id}",
    response_model=FareAuditResponse,
    dependencies=[Depends(verify_auditor_credentials)],
)
def get_trip_fare_audit(
    trip_id: uuid.UUID = Path(..., description="UUID de la solicitud de viaje a auditar"),
    db: Session = Depends(get_db),
):
    """
    Reconstruye matemáticamente cómo se calculó la tarifa de cualquier viaje (RF-04, CA-05).
    Muestra multiplicador, presión, clima, versión de reglas y estado de degradación.
    """
    result = audit_service.reconstruct_fare_audit(db, trip_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró registro de auditoría para el viaje {trip_id}.",
        )
    return result
