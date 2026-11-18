from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_booking, set_booking_created_at


async def test_dedup_replay_returns_same_booking(
    client: AsyncClient, event_id: int
) -> None:
    first = await create_booking(
        client, user_id=1, event_id=event_id, count=2, dedup_id=5001
    )
    second = await create_booking(
        client, user_id=1, event_id=event_id, count=2, dedup_id=5001
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["status"] == "pending"


async def test_dedup_conflict_on_different_payload(
    client: AsyncClient, event_id: int
) -> None:
    first = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=5002
    )
    assert first.status_code == 201

    conflict_count = await create_booking(
        client, user_id=1, event_id=event_id, count=2, dedup_id=5002
    )
    assert conflict_count.status_code == 409


async def test_dedup_after_cancel_does_not_recreate(
    client: AsyncClient, event_id: int
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=5003
    )
    booking_id = created.json()["id"]
    cancelled = await client.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    assert cancelled.status_code == 200

    replay = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=5003
    )
    assert replay.status_code == 409
    assert "cancelled" in replay.json()["detail"]


async def test_dedup_after_expire_does_not_recreate(
    client: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=5004
    )
    booking_id = created.json()["id"]
    await set_booking_created_at(
        session,
        booking_id,
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=15),
    )

    got = await client.get(f"/bookings/{booking_id}", headers=auth_headers(1))
    assert got.json()["status"] == "expired"

    replay = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=5004
    )
    assert replay.status_code == 409
    assert "expired" in replay.json()["detail"]
