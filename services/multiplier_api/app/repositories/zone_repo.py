# app/repositories/zone_repo.py
from collections import defaultdict
from app.models.zone import Zone
from app.models.zone_state import ZoneStateHistory
from sqlalchemy import func
from sqlalchemy.orm import Session


def get_by_id(db: Session, zone_id: int) -> Zone | None:
    # Lectura por clave primaria.
    return db.get(Zone, zone_id)


def get_underserved_zones(
    db: Session,
    threshold_minutes: float = 12.0,
    consecutive_intervals: int = 3,
) -> list[dict]:
    """
    Detecta zonas desatendidas (RN-08): tiempo de espera estimado > 12 minutos
    durante 3 intervalos consecutivos de cálculo.
    """
    # Subconsulta con función ventana row_number() sobre los últimos intervalos por zona
    subq = (
        db.query(
            ZoneStateHistory.zone_id,
            ZoneStateHistory.estimated_wait_minutes,
            ZoneStateHistory.interval_start,
            func.row_number()
            .over(
                partition_by=ZoneStateHistory.zone_id,
                order_by=ZoneStateHistory.interval_start.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )

    recent_intervals = (
        db.query(
            subq.c.zone_id,
            subq.c.estimated_wait_minutes,
            Zone.zone_name,
            Zone.borough,
        )
        .join(Zone, subq.c.zone_id == Zone.zone_id)
        .filter(subq.c.rn <= consecutive_intervals)
        .all()
    )

    zone_data: dict[int, dict] = defaultdict(
        lambda: {"waits": [], "zone_name": "", "borough": ""}
    )
    for zid, wait, name, borough in recent_intervals:
        if wait is not None:
            zone_data[zid]["waits"].append(float(wait))
        zone_data[zid]["zone_name"] = name
        zone_data[zid]["borough"] = borough

    underserved = []
    for zid, data in zone_data.items():
        waits = data["waits"]
        if len(waits) >= consecutive_intervals and all(w > threshold_minutes for w in waits):
            avg_wait = round(sum(waits) / len(waits), 1)
            recommended_veh = max(5, int(avg_wait * 1.5))
            underserved.append({
                "zone_id": zid,
                "zone_name": data["zone_name"],
                "borough": data["borough"],
                "consecutive_intervals": len(waits),
                "avg_estimated_wait_minutes": avg_wait,
                "recommended_additional_vehicles": recommended_veh,
            })

    underserved.sort(key=lambda x: x["avg_estimated_wait_minutes"], reverse=True)
    return underserved

