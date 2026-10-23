# app/services/audit_service.py
import uuid

from app.repositories import fare_audit_repo
from app.schemas.audit import FareAuditResponse
from sqlalchemy.orm import Session


def reconstruct_fare_audit(
    db: Session, trip_id: uuid.UUID
) -> FareAuditResponse | None:
    """
    Reconstruye matemáticamente cómo se calculó la tarifa de cualquier viaje (RF-04, CA-05).
    Lee los valores históricos persistidos en fare_audit de forma inmutable.
    """
    audit = fare_audit_repo.get_by_trip_id(db, trip_id)
    if audit is None:
        return None

    # Verifica si en el momento del cálculo coincidía con un fallback degradado
    degraded = float(audit.multiplier) == 1.0 and audit.pressure_index > 1.2

    return FareAuditResponse(
        trip_id=audit.trip_id,
        base_fare=float(audit.base_fare),
        multiplier=float(audit.multiplier),
        charged_fare=float(audit.charged_fare),
        pressure_index=float(audit.pressure_index),
        rain_mm_h=float(audit.rain_mm_h),
        rule_version_id=audit.rule_version_id,
        degraded=degraded,
    )
