# app/schemas/zone.py
from pydantic import BaseModel, ConfigDict


class NameZone(BaseModel):
    # from_attributes permite devolver el objeto SQLAlchemy directamente.
    model_config = ConfigDict(from_attributes=True)

    zone_id: int
    zone_name: str
    borough: str


class UnderservedZoneResponse(BaseModel):
    zone_id: int
    zone_name: str
    borough: str
    consecutive_intervals: int
    avg_estimated_wait_minutes: float
    recommended_additional_vehicles: int

