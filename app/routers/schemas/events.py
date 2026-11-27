from pydantic import BaseModel


class EventResponse(BaseModel):
    id: int
    capacity: int

    model_config = {"from_attributes": True}


class AvailabilityResponse(BaseModel):
    event_id: int
    available: int
