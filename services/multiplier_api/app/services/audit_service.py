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


def recalculate_period_tariffs(
    db: Session,
    start_date,
    end_date,
    rule_version_id: int,
):
    """
    Recalcula retrospectivamente las tarifas de un periodo bajo una versión específica de reglas (RF-08).
    Permite evaluar el impacto de escenarios tarifarios sin alterar los datos originales.
    """
    from decimal import Decimal
    from fastapi import HTTPException, status
    from app.models.fare_audit import FareAudit
    from app.models.tariff_rule_version import TariffRuleVersion
    from app.models.trip_request import TripRequest
    from app.schemas.audit import RecalculatePeriodResponse

    rule_ver = (
        db.query(TariffRuleVersion)
        .filter(TariffRuleVersion.rule_version_id == rule_version_id)
        .first()
    )
    if not rule_ver:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Versión de regla tarifaria {rule_version_id} no encontrada.",
        )

    audits = (
        db.query(FareAudit)
        .join(TripRequest, FareAudit.trip_id == TripRequest.trip_id)
        .filter(TripRequest.requested_at >= start_date, TripRequest.requested_at <= end_date)
        .all()
    )

    original_rev = Decimal("0.00")
    recalculated_rev = Decimal("0.00")
    max_cap = Decimal(str(rule_ver.rules.get("max_multiplier", 2.0)))

    for audit in audits:
        original_rev += audit.charged_fare
        # Simular multiplicador acotado por la versión seleccionada
        simulated_mult = min(audit.multiplier, max_cap)
        simulated_fare = (audit.base_fare * simulated_mult).quantize(Decimal("0.01"))
        recalculated_rev += simulated_fare

    diff = recalculated_rev - original_rev
    pct = float((diff / original_rev * 100)) if original_rev > 0 else 0.0

    rule_name = f"Regla v{rule_version_id} (Válida desde {rule_ver.valid_from})"

    return RecalculatePeriodResponse(
        rule_version_id=rule_ver.rule_version_id,
        rule_version_name=rule_name,
        period_start=start_date,
        period_end=end_date,
        total_trips_evaluated=len(audits),
        original_total_revenue=float(original_rev),
        recalculated_total_revenue=float(recalculated_rev),
        revenue_difference=float(diff),
        percentage_change=round(pct, 2),
    )

