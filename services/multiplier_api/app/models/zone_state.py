# app/models/zone_state.py
from datetime import datetime
from decimal import Decimal

from app.core.database import Base
from sqlalchemy import DateTime, Float, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column


class ZoneState(Base):
    """Valor vigente del multiplicador por zona (una fila por zona)."""

    __tablename__ = "zone_state"

    zone_id: Mapped[int] = mapped_column(primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pressure_index: Mapped[float] = mapped_column(Float, default=1.0)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    free_vehicles: Mapped[int] = mapped_column(Integer, default=0)
    requests_last_10min: Mapped[int] = mapped_column(Integer, default=0)
