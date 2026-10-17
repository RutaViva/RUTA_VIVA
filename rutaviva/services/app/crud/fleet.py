from datetime import date
from sqlalchemy import select, not_, or_, and_
from sqlalchemy.orm import Session
from services.app.models.fleet import Driver, License, Sanction

def get_available_supply(db: Session, query_date: date = None):
    if query_date is None:
        query_date = date.today()

    # Subconsulta de conductores con sanciones vigentes en la fecha consultada
    active_suspension_subquery = (
        select(Sanction.driver_id)
        .where(
            and_(
                Sanction.starts_on <= query_date,
                or_(Sanction.ends_on.is_(None), Sanction.ends_on >= query_date)
            )
        )
    )

    # Consulta principal: conductores activos, con licencia no vencida y sin sanción activa
    available_drivers = (
        db.query(Driver)
        .join(License, Driver.driver_id == License.driver_id)
        .filter(
            Driver.status == "active",
            License.expires_on >= query_date,
            not_(Driver.driver_id.in_(active_suspension_subquery))
        )
        .all()
    )

    return available_drivers