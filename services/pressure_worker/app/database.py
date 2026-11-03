# services/pressure_worker/app/database.py
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from worker_config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60, # Segundos a esperar antes de lanzar TimeoutError
    pool_recycle=1800, # Recicla conexiones tras 30 min (evita caídas por inactividad)
    pool_pre_ping=True, # Comprueba que la conexión siga viva antes de usarla
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def get_db_session():
    """Context manager para transacciones de base de datos seguras."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
