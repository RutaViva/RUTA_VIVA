from datetime import date
from sqlalchemy import select, not_, or_, and_
from sqlalchemy.orm import Session, joinedload
from services.app.models.fleet import Driver, License, Sanction, Vehicle, VehicleState

def _active_suspension_subquery(query_date: date):
    return (
        select(Sanction.driver_id)
        .where(
            and_(
                Sanction.starts_on <= query_date,
                or_(Sanction.ends_on.is_(None), Sanction.ends_on >= query_date)
            )
        )
    )

def get_available_supply(db: Session, query_date: date = None):
    """
    Retorna los conductores aptos en la oferta según RN-09
    (activos, con licencia vigente y sin sanciones activas), cargando su vehículo.
    """
    if query_date is None:
        query_date = date.today()

    subquery = _active_suspension_subquery(query_date)

    return (
        db.query(Driver)
        .options(joinedload(Driver.vehicle).joinedload(Vehicle.state))
        .join(License, Driver.driver_id == License.driver_id)
        .filter(
            Driver.status == "active",
            License.expires_on >= query_date,
            not_(Driver.driver_id.in_(subquery))
        )
        .all()
    )

def get_available_vehicles(db: Session, query_date: date = None, zone_id: int = None):
    """
    Retorna únicamente los vehículos cuyos conductores cumplen RN-09.
    Aunque el vehículo tenga estado activo en vehicle_state, si su conductor está
    inactivo, suspendido o con licencia vencida, queda excluido de la oferta.
    """
    if query_date is None:
        query_date = date.today()

    subquery = _active_suspension_subquery(query_date)

    query = (
        db.query(Vehicle)
        .options(joinedload(Vehicle.driver), joinedload(Vehicle.state))
        .join(Driver, Vehicle.driver_id == Driver.driver_id)
        .join(License, Driver.driver_id == License.driver_id)
        .filter(
            Driver.status == "active",
            License.expires_on >= query_date,
            not_(Driver.driver_id.in_(subquery))
        )
    )

    if zone_id is not None:
        query = query.join(VehicleState, Vehicle.vehicle_id == VehicleState.vehicle_id).filter(
            VehicleState.zone_id == zone_id
        )

    return query.all()