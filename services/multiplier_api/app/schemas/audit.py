# app/schemas/audit.py
import uuid

from pydantic import BaseModel


class FareAuditResponse(BaseModel):
    trip_id: uuid.UUID
    base_fare: float
    multiplier: float
    charged_fare: float
    pressure_index: float
    rain_mm_h: float
    rule_version_id: int
    degraded: bool
