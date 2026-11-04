import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ComplaintCategory = Literal["service", "fare", "safety", "other"]


class ServiceComplaintCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ComplaintCategory


class ServiceComplaintResponse(BaseModel):
    complaint_id: uuid.UUID
    trip_id: uuid.UUID
    created_at: datetime
    category: ComplaintCategory

    model_config = {"from_attributes": True}
