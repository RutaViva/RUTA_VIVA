"""
Módulo de modelos ORM utilizando SQLAlchemy 2.0.
Representa exactamente la estructura del esquema relacional.
"""

import uuid
from datetime import date, datetime
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Driver(Base):
    __tablename__ = "driver"

    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)


class Vehicle(Base):
    __tablename__ = "vehicle"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    plate: Mapped[str] = mapped_column(String(15), nullable=False, unique=True)


class License(Base):
    __tablename__ = "license"

    license_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    expires_on: Mapped[date] = mapped_column(Date, nullable=False)


class Sanction(Base):
    __tablename__ = "sanction"

    sanction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    driver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)


class Zone(Base):
    __tablename__ = "zone"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    borough: Mapped[str] = mapped_column(String(80), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(100), nullable=False)


class VehicleState(Base):
    __tablename__ = "vehicle_state"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("vehicle.vehicle_id"), primary_key=True)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ZoneState(Base):
    __tablename__ = "zone_state"

    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    free_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_last_10min: Mapped[int] = mapped_column(Integer, nullable=False)


class ZoneStateHistory(Base):
    __tablename__ = "zone_state_history"

    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), primary_key=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False)
    free_vehicles: Mapped[int] = mapped_column(Integer, nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_wait_minutes: Mapped[float] = mapped_column(Float, nullable=False)


class TripRequest(Base):
    __tablename__ = "trip_request"

    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)


class TariffRuleVersion(Base):
    __tablename__ = "tariff_rule_version"

    rule_version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)


class FareAudit(Base):
    __tablename__ = "fare_audit"

    trip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("trip_request.trip_id"), primary_key=True)
    base_fare: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    charged_fare: Mapped[float] = mapped_column(Float, nullable=False)
    pressure_index: Mapped[float] = mapped_column(Float, nullable=False)
    rain_mm_h: Mapped[float] = mapped_column(Float, nullable=False)
    rule_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("tariff_rule_version.rule_version_id"), nullable=False)


class SpecialEvent(Base):
    __tablename__ = "special_event"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zone.zone_id"), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WeatherCurrent(Base):
    __tablename__ = "weather_current"

    valid_hour: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    rain_mm_h: Mapped[float] = mapped_column(Float, nullable=False)