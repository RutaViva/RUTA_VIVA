# app/models/zone.py
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Zone(Base):
    """Catálogo de zonas (F2)."""

    __tablename__ = "zone"

    zone_id: Mapped[int] = mapped_column(primary_key=True)
    borough: Mapped[str]
    zone_name: Mapped[str]