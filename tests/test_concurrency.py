import asyncio

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_booking


async def test_hundred_parallel_bookings_fill_exactly_capacity(
    client: AsyncClient, client_b: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    async def book(user_id: int, http: AsyncClient):
        return await create_booking(
            http,
            user_id=user_id,
            event_id=event_id,
            count=1,
            dedup_id=10_000 + user_id,
        )

    tasks = [
        book(user_id, client if user_id % 2 else client_b)
        for user_id in range(1, 101)
    ]
    responses = await asyncio.gather(*tasks)

    created = [r for r in responses if r.status_code == 201]
    rejected = [r for r in responses if r.status_code == 409]
    assert len(created) == 10
    assert len(rejected) == 90
    assert all("Not enough seats" in r.json()["detail"] for r in rejected)

    ids = {r.json()["id"] for r in created}
    assert len(ids) == 10

    avail = await client.get(f"/events/{event_id}/availability")
    assert avail.json()["available"] == 0


async def test_parallel_same_dedup_key_returns_same_booking(
    client: AsyncClient, client_b: AsyncClient, event_id: int
) -> None:
    async def book(http: AsyncClient):
        return await create_booking(
            http, user_id=1, event_id=event_id, count=1, dedup_id=777
        )

    responses = await asyncio.gather(
        *(book(client if i % 2 else client_b) for i in range(20))
    )
    assert all(r.status_code == 201 for r in responses)
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1
    assert all(r.json()["status"] == "pending" for r in responses)


async def test_confirm_vs_cancel_race(
    client: AsyncClient, client_b: AsyncClient, event_id: int, session: AsyncSession
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, count=1, dedup_id=888
    )
    booking_id = created.json()["id"]

    confirm_task = client.post(
        f"/bookings/{booking_id}/confirm", headers=auth_headers(1)
    )
    cancel_task = client_b.post(
        f"/bookings/{booking_id}/cancel", headers=auth_headers(1)
    )
    confirm_resp, cancel_resp = await asyncio.gather(confirm_task, cancel_task)

    statuses = {confirm_resp.status_code, cancel_resp.status_code}
    assert 200 in statuses
    assert 409 in statuses

    row = (
        await session.execute(
            text(
                "SELECT confirmed, cancelled_at IS NOT NULL FROM bookings WHERE id = :id"
            ),
            {"id": booking_id},
        )
    ).one()
    confirmed, cancelled = bool(row[0]), bool(row[1])
    assert confirmed != cancelled
