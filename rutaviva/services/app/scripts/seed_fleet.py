from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from services.app.models.fleet import Driver, License, Vehicle, Sanction

def seed_database(db: Session):
    """
    Ejecuta un seed idempotente sobre PostgreSQL utilizando ON CONFLICT DO NOTHING
    para preservar la integridad referencial sin duplicados.
    """
    for d in db.query(Driver).all():
        stmt = pg_insert(Driver).values(
            driver_id=d.driver_id,
            full_name=d.full_name,
            status=d.status
        ).on_conflict_do_nothing(index_elements=["driver_id"])
        db.execute(stmt)

    for lic in db.query(License).all():
        stmt = pg_insert(License).values(
            license_id=lic.license_id,
            driver_id=lic.driver_id,
            expires_on=lic.expires_on
        ).on_conflict_do_nothing(index_elements=["license_id"])
        db.execute(stmt)

    for v in db.query(Vehicle).all():
        stmt = pg_insert(Vehicle).values(
            vehicle_id=v.vehicle_id,
            driver_id=v.driver_id,
            plate=v.plate
        ).on_conflict_do_nothing(index_elements=["vehicle_id"])
        db.execute(stmt)

    for s in db.query(Sanction).all():
        stmt = pg_insert(Sanction).values(
            sanction_id=s.sanction_id,
            driver_id=s.driver_id,
            starts_on=s.starts_on,
            ends_on=s.ends_on
        ).on_conflict_do_nothing(index_elements=["sanction_id"])
        db.execute(stmt)

    db.commit()