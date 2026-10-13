# app/schemas/multiplier.py
from datetime import datetime

from pydantic import BaseModel


class MultiplierResponse(BaseModel):
    zone_id: int
    multiplier: float
    computed_at: datetime | None  # None cuando no hay dato (degradado)
    degraded: bool  # True = 1.0 por fallback, no calculado