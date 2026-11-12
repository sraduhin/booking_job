from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import literal_column

from app.config import get_settings
from app.models import Booking, Event
from app.routers.schemas.bookings import BookingStatus


class BookingError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def booking_ttl() -> timedelta:
    return timedelta(minutes=get_settings().booking_ttl_minutes)


def ttl_interval():
    minutes = get_settings().booking_ttl_minutes
    return literal_column(f"INTERVAL '{minutes} minutes'")


def expires_at(created_at: datetime) -> datetime:
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    return created + booking_ttl()


def resolve_status(booking: Booking, *, now: datetime | None = None) -> BookingStatus:
    if booking.cancelled_at is not None:
        return BookingStatus.cancelled
    if booking.confirmed:
        return BookingStatus.confirmed
    current = now or datetime.now(timezone.utc)
    created = (
        booking.created_at
        if booking.created_at.tzinfo
        else booking.created_at.replace(tzinfo=timezone.utc)
    )
    if created + booking_ttl() <= current:
        return BookingStatus.expired
    return BookingStatus.pending


def _active_booking_filter(event_id: int):
    return (
        Booking.event_id == event_id,
        Booking.cancelled_at.is_(None),
        (
            (Booking.confirmed.is_(True))
            | (Booking.created_at > func.clock_timestamp() - ttl_interval())
        ),
    )


async def get_availability(session: AsyncSession, event_id: int) -> int:
    occupied = occupied_seats_expr(Event.id)
    result = await session.scalar(
        select(Event.capacity - occupied).where(Event.id == event_id)
    )
    if result is None:
        raise BookingError(404, "Event not found")
    return int(result)


def occupied_seats_expr(event_id_column=Event.id):
    return (
        select(func.coalesce(func.sum(Booking.count), 0))
        .where(
            Booking.event_id == event_id_column,
            Booking.cancelled_at.is_(None),
            (
                (Booking.confirmed.is_(True))
                | (Booking.created_at > func.clock_timestamp() - ttl_interval())
            ),
        )
        .scalar_subquery()
    )


async def _lock_event(session: AsyncSession, event_id: int) -> Event:
    stmt: Select[tuple[Event]] = (
        select(Event).where(Event.id == event_id).with_for_update()
    )
    event = await session.scalar(stmt)
    if event is None:
        raise BookingError(404, "Event not found")
    return event


async def _get_by_dedup(
    session: AsyncSession,
    user_id: int,
    dedup_id: int,
    *,
    for_update: bool = False,
) -> Booking | None:
    stmt = select(Booking).where(
        Booking.user_id == user_id,
        Booking.dedup_id == dedup_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def _get_booking(
    session: AsyncSession,
    booking_id: int,
    user_id: int,
    *,
    for_update: bool = False,
) -> Booking:
    stmt = select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    booking = await session.scalar(stmt)
    if booking is None:
        raise BookingError(404, "Booking not found")
    return booking


def _assert_dedup_match(booking: Booking, event_id: int, count: int) -> None:
    if booking.event_id != event_id or booking.count != count:
        raise BookingError(
            409,
            "Dedup-Id already used with different event_id or count",
        )
    status = resolve_status(booking)
    if status in (BookingStatus.cancelled, BookingStatus.expired):
        raise BookingError(
            409,
            f"Dedup-Id already used by a {status.value} booking",
        )


async def create_booking(
    session: AsyncSession,
    *,
    user_id: int,
    event_id: int,
    count: int,
    dedup_id: int,
) -> Booking:
    await _lock_event(session, event_id)

    existing = await _get_by_dedup(session, user_id, dedup_id, for_update=True)
    if existing is not None:
        _assert_dedup_match(existing, event_id, count)
        await session.commit()
        return existing

    occupied = await session.scalar(
        select(func.coalesce(func.sum(Booking.count), 0)).where(
            *_active_booking_filter(event_id)
        )
    )
    capacity = await session.scalar(select(Event.capacity).where(Event.id == event_id))
    if occupied is None or capacity is None:
        raise BookingError(404, "Event not found")
    if int(occupied) + count > int(capacity):
        raise BookingError(409, "Not enough seats available")

    booking = Booking(
        user_id=user_id,
        event_id=event_id,
        count=count,
        dedup_id=dedup_id,
    )
    session.add(booking)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _get_by_dedup(session, user_id, dedup_id)
        if existing is None:
            raise BookingError(409, "Failed to create booking") from None
        _assert_dedup_match(existing, event_id, count)
        return existing

    await session.refresh(booking)
    return booking


async def get_booking(session: AsyncSession, booking_id: int, user_id: int) -> Booking:
    return await _get_booking(session, booking_id, user_id)


async def confirm_booking(session: AsyncSession, booking_id: int, user_id: int) -> Booking:
    booking = await _get_booking(session, booking_id, user_id)
    await _lock_event(session, booking.event_id)
    booking = await _get_booking(session, booking_id, user_id, for_update=True)

    status = resolve_status(booking)
    if status == BookingStatus.confirmed:
        await session.commit()
        return booking
    if status == BookingStatus.cancelled:
        raise BookingError(409, "Cannot confirm a cancelled booking")
    if status == BookingStatus.expired:
        raise BookingError(409, "Cannot confirm an expired booking")

    result = await session.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.user_id == user_id,
            Booking.cancelled_at.is_(None),
            Booking.confirmed.is_(False),
            Booking.created_at > func.clock_timestamp() - ttl_interval(),
        )
        .values(confirmed=True)
        .returning(Booking.id)
    )
    if result.first() is None:
        await session.refresh(booking)
        status = resolve_status(booking)
        if status == BookingStatus.confirmed:
            await session.commit()
            return booking
        if status == BookingStatus.cancelled:
            raise BookingError(409, "Cannot confirm a cancelled booking")
        raise BookingError(409, "Cannot confirm an expired booking")

    await session.commit()
    await session.refresh(booking)
    return booking


async def cancel_booking(
    session: AsyncSession, booking_id: int, user_id: int
) -> Booking:
    booking = await _get_booking(session, booking_id, user_id)
    await _lock_event(session, booking.event_id)
    booking = await _get_booking(session, booking_id, user_id, for_update=True)

    status = resolve_status(booking)
    if status == BookingStatus.cancelled:
        await session.commit()
        return booking
    if status == BookingStatus.confirmed:
        raise BookingError(409, "Cannot cancel a confirmed booking")
    if status == BookingStatus.expired:
        raise BookingError(409, "Cannot cancel an expired booking")

    result = await session.execute(
        update(Booking)
        .where(
            Booking.id == booking_id,
            Booking.user_id == user_id,
            Booking.cancelled_at.is_(None),
            Booking.confirmed.is_(False),
            Booking.created_at > func.clock_timestamp() - ttl_interval(),
        )
        .values(cancelled_at=func.clock_timestamp())
        .returning(Booking.id)
    )
    if result.first() is None:
        await session.refresh(booking)
        status = resolve_status(booking)
        if status == BookingStatus.cancelled:
            await session.commit()
            return booking
        if status == BookingStatus.confirmed:
            raise BookingError(409, "Cannot cancel a confirmed booking")
        raise BookingError(409, "Cannot cancel an expired booking")

    await session.commit()
    await session.refresh(booking)
    return booking
