import enum
import uuid
from sqlalchemy import Column, Integer, String, Date, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from services.app.database import Base

class LicenseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"

class SanctionType(str, enum.Enum):
    SUSPENSION = "SUSPENSION"
    FINE = "FINE"
    WARNING = "WARNING"

class Driver(Base):
    __tablename__ = "driver"

    driver_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    full_name = Column(String(200), nullable=False)
    status = Column(String(50), nullable=False, default="active")

    license = relationship("License", back_populates="driver", uselist=False)
    sanctions = relationship("Sanction", back_populates="driver")
    vehicle = relationship("Vehicle", back_populates="driver", uselist=False)

class Vehicle(Base):
    __tablename__ = "vehicle"

    vehicle_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), unique=True, nullable=True)
    plate = Column(String(20), unique=True, nullable=False, index=True)

    driver = relationship("Driver", back_populates="vehicle")
    state = relationship("VehicleState", back_populates="vehicle", uselist=False)

class VehicleState(Base):
    __tablename__ = "vehicle_state"

    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicle.vehicle_id"), primary_key=True, index=True)
    zone_id = Column(Integer, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(String(50), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

    vehicle = relationship("Vehicle", back_populates="state")

class License(Base):
    __tablename__ = "license"

    license_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), unique=True, nullable=False)
    expires_on = Column(Date, nullable=False)

    driver = relationship("Driver", back_populates="license")

class Sanction(Base):
    __tablename__ = "sanction"

    sanction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("driver.driver_id"), nullable=False)
    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=True)

    driver = relationship("Driver", back_populates="sanctions")