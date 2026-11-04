import uuid
from datetime import datetime

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


class RecalculatePeriodRequest(BaseModel):
    start_date: datetime
    end_date: datetime
    rule_version_id: int


class RecalculatePeriodResponse(BaseModel):
    rule_version_id: int
    rule_version_name: str
    period_start: datetime
    period_end: datetime
    total_trips_evaluated: int
    original_total_revenue: float
    recalculated_total_revenue: float
    revenue_difference: float
    percentage_change: float

