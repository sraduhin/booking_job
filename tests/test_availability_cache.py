from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

from app import cache
from app.config import get_settings
from tests.conftest import create_booking


@pytest.mark.asyncio
async def test_availability_cache_miss_then_hit(
    client: AsyncClient, event_id: int, redis_client: Redis
) -> None:
    key = f"event:{event_id}:availability"
    assert await redis_client.get(key) is None

    first = await client.get(f"/events/{event_id}/availability")
    assert first.status_code == 200
    assert first.json() == {"event_id": event_id, "available": 10}
    assert await redis_client.get(key) is not None

    # Меняем значение в Redis - hit должен вернуть его, а не БД
    await redis_client.set(key, "0:7", ex=10)
    second = await client.get(f"/events/{event_id}/availability")
    assert second.status_code == 200
    assert second.json()["available"] == 7


@pytest.mark.asyncio
async def test_create_booking_invalidates_cache(
    client: AsyncClient, event_id: int, redis_client: Redis
) -> None:
    warm = await client.get(f"/events/{event_id}/availability")
    assert warm.json()["available"] == 10
    key = f"event:{event_id}:availability"
    assert await redis_client.get(key) is not None

    created = await create_booking(
        client, user_id=1, event_id=event_id, dedup_id=1
    )
    assert created.status_code == 201
    assert await redis_client.get(key) is None

    after = await client.get(f"/events/{event_id}/availability")
    assert after.json()["available"] == 9


@pytest.mark.asyncio
async def test_cancel_booking_invalidates_cache(
    client: AsyncClient, event_id: int, redis_client: Redis
) -> None:
    created = await create_booking(
        client, user_id=1, event_id=event_id, dedup_id=2
    )
    booking_id = created.json()["id"]

    warm = await client.get(f"/events/{event_id}/availability")
    assert warm.json()["available"] == 9
    key = f"event:{event_id}:availability"
    assert await redis_client.get(key) is not None

    cancelled = await client.post(
        f"/bookings/{booking_id}/cancel",
        headers={"X-User-Id": "1"},
    )
    assert cancelled.status_code == 200
    assert await redis_client.get(key) is None

    after = await client.get(f"/events/{event_id}/availability")
    assert after.json()["available"] == 10


@pytest.mark.asyncio
async def test_cache_ttl_expiry(
    client: AsyncClient, event_id: int, redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AVAILABILITY_CACHE_TTL_SECONDS", "1")
    get_settings.cache_clear()

    first = await client.get(f"/events/{event_id}/availability")
    assert first.json()["available"] == 10
    key = f"event:{event_id}:availability"
    assert await redis_client.get(key) is not None

    await asyncio.sleep(1.2)
    assert await redis_client.get(key) is None

    # После TTL - снова miss и запись из БД
    second = await client.get(f"/events/{event_id}/availability")
    assert second.json()["available"] == 10
    assert await redis_client.get(key) is not None

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_db(
    client: AsyncClient, event_id: int
) -> None:
    cache.set_redis(None)

    response = await client.get(f"/events/{event_id}/availability")
    assert response.status_code == 200
    assert response.json()["available"] == 10

    created = await create_booking(
        client, user_id=1, event_id=event_id, dedup_id=3
    )
    assert created.status_code == 201


@pytest.mark.asyncio
async def test_booking_ignores_stale_cache(
    client: AsyncClient, event_id: int, redis_client: Redis
) -> None:
    # Кэш врёт: «ещё 10 мест», хотя в БД мест нет
    for i in range(10):
        resp = await create_booking(
            client, user_id=i + 1, event_id=event_id, dedup_id=100 + i
        )
        assert resp.status_code == 201

    # Подсовываем устаревшее «10 свободных» с актуальным generation - GET врёт, PG нет
    gen = await redis_client.get(f"event:{event_id}:avail_gen") or "0"
    await redis_client.set(f"event:{event_id}:availability", f"{gen}:10", ex=10)
    assert (await client.get(f"/events/{event_id}/availability")).json()[
        "available"
    ] == 10

    denied = await create_booking(
        client, user_id=50, event_id=event_id, dedup_id=999
    )
    assert denied.status_code == 409
    assert denied.json()["detail"] == "Not enough seats available"


@pytest.mark.asyncio
async def test_stale_write_back_after_invalidate_is_rejected(
    event_id: int, redis_client: Redis
) -> None:
    generation = await cache.read_generation(event_id)
    assert generation == "0"

    # Параллельно: «прочитали БД», затем инвалидация, затем попытка записи
    await cache.invalidate_availability(event_id)
    written = await cache.set_cached_availability(event_id, 10, generation)
    assert written is False
    assert await redis_client.get(f"event:{event_id}:availability") is None

    # Актуальная запись с новым generation проходит
    new_gen = await cache.read_generation(event_id)
    assert new_gen == "1"
    assert await cache.set_cached_availability(event_id, 9, new_gen) is True
    assert await cache.get_cached_availability(event_id) == 9
