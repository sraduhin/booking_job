from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_booking


async def test_create_get_confirm_cancel_flow(
    client: AsyncClient, event_id: int
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=2, dedup_id=1001
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["count"] == 2
    booking_id = body["id"]

    got = await client.get(
        f"/bookings/{booking_id}", headers=auth_headers(1)
    )
    assert got.status_code == 200
    assert got.json()["id"] == booking_id

    confirmed = await client.post(
        f"/bookings/{booking_id}/confirm", headers=auth_headers(1)
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    again = await client.post(
        f"/bookings/{booking_id}/confirm", headers=auth_headers(1)
    )
    assert again.status_code == 200
    assert again.json()["status"] == "confirmed"

    cancel_confirmed = await client.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    assert cancel_confirmed.status_code == 409


async def test_cancel_pending_and_rebook(
    client: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=5, dedup_id=2001
    )
    assert created.status_code == 201
    booking_id = created.json()["id"]

    avail = await client.get(f"/events/{event_id}/availability")
    assert avail.status_code == 200
    assert avail.json()["available"] == 5

    cancelled = await client.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    again_cancel = await client.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    assert again_cancel.status_code == 200
    assert again_cancel.json()["status"] == "cancelled"

    avail_after = await client.get(f"/events/{event_id}/availability")
    assert avail_after.json()["available"] == 10

    rebook = await create_booking(
        client, user_id=2, event_id=event_id, count=5, dedup_id=2002
    )
    assert rebook.status_code == 201


async def test_not_enough_seats(client: AsyncClient, event_id: int) -> None:
    first = await create_booking(
        client, user_id=1, event_id=event_id, count=5, dedup_id=3001
    )
    second = await create_booking(
        client, user_id=2, event_id=event_id, count=5, dedup_id=3002
    )
    assert first.status_code == 201
    assert second.status_code == 201

    third = await create_booking(
        client, user_id=3, event_id=event_id, count=1, dedup_id=3003
    )
    assert third.status_code == 409
    assert "Not enough seats" in third.json()["detail"]


async def test_ownership_foreign_booking_is_404(
    client: AsyncClient, event_id: int
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=4001
    )
    booking_id = created.json()["id"]

    for method, path in (
        ("get", f"/bookings/{booking_id}"),
        ("post", f"/bookings/{booking_id}/confirm"),
        ("post", f"/bookings/{booking_id}/cancel"),
    ):
        response = await getattr(client, method)(path, headers=auth_headers(2))
        assert response.status_code == 404, path


async def test_list_events(client: AsyncClient, event_id: int) -> None:
    response = await client.get("/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["id"] == event_id
    assert events[0]["capacity"] == 10
