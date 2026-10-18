# app/models/trip_request.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TripRequest(Base):
    __tablename__ = "trip_request"

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")

    audit: Mapped["FareAudit"] = relationship("FareAudit", back_populates="trip", uselist=False)
