# app/models/fare_audit.py
import uuid
from decimal import Decimal

from sqlalchemy import Float, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FareAudit(Base):
    __tablename__ = "fare_audit"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_request.trip_id"), primary_key=True
    )
    base_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    charged_fare: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    rain_mm_h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rule_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tariff_rule_version.rule_version_id"), nullable=False
    )

    trip: Mapped["TripRequest"] = relationship("TripRequest", back_populates="audit")
