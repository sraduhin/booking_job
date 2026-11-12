from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user_id, get_dedup_id
from app.models import Booking
from app.routers.schemas.bookings import BookingCreate, BookingResponse
from app.routers.schemas import ErrorResponse
from app.services import booking as booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])


def to_response(booking: Booking) -> BookingResponse:
    return BookingResponse(
        id=booking.id,
        event_id=booking.event_id,
        user_id=booking.user_id,
        count=booking.count,
        status=booking_service.resolve_status(booking),
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
        expires_at=booking_service.expires_at(booking.created_at),
        dedup_id=booking.dedup_id,
    )


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_booking(
    payload: BookingCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    dedup_id: Annotated[int, Depends(get_dedup_id)],
) -> BookingResponse:
    try:
        booking = await booking_service.create_booking(
            session,
            user_id=user_id,
            event_id=payload.event_id,
            count=payload.count,
            dedup_id=dedup_id,
        )
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_response(booking)


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def get_booking(
    booking_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> BookingResponse:
    try:
        booking = await booking_service.get_booking(session, booking_id, user_id)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_response(booking)


@router.post(
    "/{booking_id}/confirm",
    response_model=BookingResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def confirm_booking(
    booking_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> BookingResponse:
    try:
        booking = await booking_service.confirm_booking(session, booking_id, user_id)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_response(booking)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def cancel_booking(
    booking_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> BookingResponse:
    try:
        booking = await booking_service.cancel_booking(session, booking_id, user_id)
    except booking_service.BookingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return to_response(booking)
