# app/models/zone_state.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ZoneState(Base):
    """Valor vigente del multiplicador por zona (una fila por zona)."""

    __tablename__ = "zone_state"

    zone_id: Mapped[int] = mapped_column(primary_key=True)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(3, 1))
    # computed_at permite detectar datos obsoletos (RNF-02, RNF-04).
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))