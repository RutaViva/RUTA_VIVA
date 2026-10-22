# app/models/weather_current.py
from datetime import datetime

from app.core.database import Base
from sqlalchemy import DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column


class WeatherCurrent(Base):
    __tablename__ = "weather_current"

    valid_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    rain_mm_h: Mapped[float] = mapped_column(Float, nullable=False)
