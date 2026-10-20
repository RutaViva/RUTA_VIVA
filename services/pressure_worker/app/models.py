# services/pressure_worker/app/models.py
import uuid
from datetime import date, datetime
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from database import Base


class Zone(Base):
    __tablename__ = "zone"
    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    borough: Mapped[str] = mapped_column(Text, nullable=False)
    zone_name: Mapped[str] = mapped_column(Text, nullable=False)


class Driver(Base):
    __tablename__ = "driver"
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicle"
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    plate: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class License(Base):
    __tablename__ = "license"
    license_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    expires_on: Mapped[date] = mapped_column(Date, nullable=False)


class Sanction(Base):
    __tablename__ = "sanction"
    sanction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)


class VehicleState(Base):
    __tablename__ = "vehicle_state"
    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicle.vehicle_id"), primary_key=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ZoneState(Base):
    __tablename__ = "zone_state"
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)
    free_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_last_10min: Mapped[int] = mapped_column(Integer, nullable=False)


class ZoneStateHistory(Base):
    __tablename__ = "zone_state_history"
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), primary_key=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)
    free_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    estimated_wait_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)


class TripRequest(Base):
    __tablename__ = "trip_request"
    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="created")


class TariffRuleVersion(Base):
    __tablename__ = "tariff_rule_version"
    rule_version_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    rules: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)


class WeatherCurrent(Base):
    __tablename__ = "weather_current"
    valid_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    rain_mm_h: Mapped[float] = mapped_column(Float, nullable=False)


class SpecialEvent(Base):
    __tablename__ = "special_event"
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
