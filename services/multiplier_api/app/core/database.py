# app/core/database.py
from app.core.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60, # Segundos a esperar antes de lanzar TimeoutError
    pool_recycle=1800, # Recicla conexiones tras 30 min (evita caídas por inactividad)
    pool_pre_ping=True, # Comprueba que la conexión siga viva antes de usarla
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Clase base de todos los modelos SQLAlchemy."""


def get_db():
    """Dependencia de FastAPI: una sesión por petición, siempre cerrada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
