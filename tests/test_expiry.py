from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_booking, set_booking_created_at


async def test_soft_expiry_blocks_confirm_and_frees_seats(
    client: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=5, dedup_id=6001
    )
    booking_id = created.json()["id"]

    await set_booking_created_at(
        session,
        booking_id,
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15),
    )

    confirm = await client.post(
        f"/bookings/{booking_id}/confirm", headers=auth_headers(1)
    )
    assert confirm.status_code == 409
    assert "expired" in confirm.json()["detail"].lower()

    got = await client.get(f"/bookings/{booking_id}", headers=auth_headers(1))
    assert got.json()["status"] == "expired"

    avail = await client.get(f"/events/{event_id}/availability")
    assert avail.json()["available"] == 10

    rebook = await create_booking(
        client, user_id=2, event_id=event_id, count=5, dedup_id=6002
    )
    assert rebook.status_code == 201


async def test_confirm_at_ttl_boundary_uses_db_clock(
    client: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=6003
    )
    booking_id = created.json()["id"]

    # Ровно за TTL + 1 секунда - бронь уже просрочена на момент UPDATE.
    await set_booking_created_at(
        session,
        booking_id,
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10, seconds=1),
    )

    confirm = await client.post(
        f"/bookings/{booking_id}/confirm", headers=auth_headers(1)
    )
    assert confirm.status_code == 409
    assert "expired" in confirm.json()["detail"].lower()


async def test_cancel_expired_is_conflict(
    client: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=6004
    )
    booking_id = created.json()["id"]
    await set_booking_created_at(
        session,
        booking_id,
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15),
    )

    cancel = await client.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    assert cancel.status_code == 409
    assert "expired" in cancel.json()["detail"].lower()
