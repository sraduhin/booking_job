from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Event
from app.routers.schemas import ErrorResponse
from app.routers.schemas.events import EventResponse, AvailabilityResponse
from app.services import booking as booking_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def list_events(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[Event]:
    result = await session.scalars(select(Event).order_by(Event.id))
    return list(result.all())


@router.get(
    "/{event_id}/availability",
    response_model=AvailabilityResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_event_availability(
    event_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AvailabilityResponse:
    try:
        available = await booking_service.get_availability(session, event_id)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AvailabilityResponse(event_id=event_id, available=available)
