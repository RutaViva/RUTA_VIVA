import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.app.models.fleet import Driver, License, Sanction
from services.app.scripts.seed_fleet import seed_database
from services.app.crud.fleet import get_available_supply

# Conectado a tu PostgreSQL real donde están los datos de RutaViva
POSTGRES_DB_URL = "postgresql+psycopg://admin:admin1234@localhost:5438/rutaviva_db"

@pytest.fixture
def db_session():
    engine = create_engine(POSTGRES_DB_URL)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()

def test_idempotent_seed(db_session):
    """
    Acceptance Criteria 2:
    Given the database populated via seed, When run twice,
    Then the data remains identical (referential integrity without duplicates).
    """
    # Corrida 1
    seed_database(db_session)
    drivers_run1 = db_session.query(Driver).count()
    licenses_run1 = db_session.query(License).count()
    sanctions_run1 = db_session.query(Sanction).count()

    # Corrida 2
    seed_database(db_session)
    drivers_run2 = db_session.query(Driver).count()
    licenses_run2 = db_session.query(License).count()
    sanctions_run2 = db_session.query(Sanction).count()

    print(f"\n📊 Corrida 1 -> Conductores: {drivers_run1}, Licencias: {licenses_run1}, Sanciones: {sanctions_run1}")
    print(f"📊 Corrida 2 -> Conductores: {drivers_run2}, Licencias: {licenses_run2}, Sanciones: {sanctions_run2}")

    assert drivers_run1 == drivers_run2 == 50
    assert licenses_run1 == licenses_run2
    assert sanctions_run1 == sanctions_run2


def test_rn_09_exclude_suspended_or_expired_drivers(db_session):
    """
    Acceptance Criteria 1:
    Given a driver with an expired or suspended license,
    When available supply is queried, Then that driver never appears in the result.
    """
    eval_date = date.today()
    available_drivers = get_available_supply(db_session, query_date=eval_date)
    available_ids = {d.driver_id for d in available_drivers}

    # 1. Buscar directamente en la BD todos los conductores con licencia expirada hoy
    expired_driver_ids = {
        lic.driver_id for lic in db_session.query(License).filter(License.expires_on < eval_date).all()
    }

    # 2. Buscar en la BD todos los conductores inactivos o suspendidos en tabla driver
    non_active_driver_ids = {
        d.driver_id for d in db_session.query(Driver).filter(Driver.status != "active").all()
    }

    # 3. Buscar en la BD todos los conductores con sanción vigente hoy
    sanctioned_driver_ids = {
        s.driver_id for s in db_session.query(Sanction).filter(
            Sanction.starts_on <= eval_date,
            (Sanction.ends_on.is_(None)) | (Sanction.ends_on >= eval_date)
        ).all()
    }

    print(f"\n🔍 Fecha de evaluación: {eval_date}")
    print(f"✅ Conductores disponibles en la oferta: {len(available_ids)}")
    print(f"❌ Conductores con licencia expirada en BD: {len(expired_driver_ids)}")
    print(f"❌ Conductores suspendidos/inactivos en BD: {len(non_active_driver_ids)}")
    print(f"❌ Conductores con sanción vigente en BD: {len(sanctioned_driver_ids)}")

    # Validación estricta RN-09: NINGÚN conductor expirado, suspendido o sancionado puede estar en available_ids
    assert available_ids.isdisjoint(expired_driver_ids), "Hay conductores con licencia vencida en la oferta!"
    assert available_ids.isdisjoint(non_active_driver_ids), "Hay conductores suspendidos/inactivos en la oferta!"
    assert available_ids.isdisjoint(sanctioned_driver_ids), "Hay conductores con sanción activa en la oferta!"