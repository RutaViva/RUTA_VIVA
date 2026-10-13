# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# pool_pre_ping verifica la conexión antes de usarla,
# así una conexión muerta no rompe la primera petición.
engine = create_engine(settings.database_url, pool_pre_ping=True)
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