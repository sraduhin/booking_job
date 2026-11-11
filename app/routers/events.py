from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Event
from app.routers.schemas.events import EventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def list_events(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[Event]:
    result = await session.scalars(select(Event).order_by(Event.id))
    return list(result.all())

