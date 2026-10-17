from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from services.app.models.fleet import Driver, License, Vehicle, Sanction

def seed_database(db: Session):
    """
    Ejecuta un seed idempotente sobre PostgreSQL utilizando ON CONFLICT DO NOTHING.
    Si los registros de la base de datos ya existen, mantiene la integridad referencial
    exactamente igual (sin duplicar filas).
    """
    existing_drivers = db.query(Driver).all()
    if existing_drivers:
        for d in existing_drivers:
            stmt = pg_insert(Driver).values(
                driver_id=d.driver_id,
                full_name=d.full_name,
                status=d.status
            ).on_conflict_do_nothing(index_elements=["driver_id"])
            db.execute(stmt)

    existing_licenses = db.query(License).all()
    if existing_licenses:
        for lic in existing_licenses:
            stmt = pg_insert(License).values(
                license_id=lic.license_id,
                driver_id=lic.driver_id,
                expires_on=lic.expires_on
            ).on_conflict_do_nothing(index_elements=["license_id"])
            db.execute(stmt)

    db.commit()