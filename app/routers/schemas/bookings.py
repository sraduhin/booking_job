from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BookingStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"


class BookingCreate(BaseModel):
    event_id: int = Field(..., ge=1)
    count: int = Field(..., ge=1, le=5)


class BookingResponse(BaseModel):
    id: int
    event_id: int
    user_id: int
    count: int
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
    expires_at: datetime
    dedup_id: int

    model_config = {"from_attributes": True}
