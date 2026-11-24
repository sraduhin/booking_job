import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def _value_key(event_id: int) -> str:
    return f"event:{event_id}:availability"


def _gen_key(event_id: int) -> str:
    return f"event:{event_id}:avail_gen"


async def init_redis() -> None:
    global _redis
    settings = get_settings()
    client = Redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    try:
        await client.ping()
    except RedisError:
        logger.warning("Redis unavailable at startup; availability will use DB")
        await client.aclose()
        _redis = None
        return
    _redis = client


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis | None:
    return _redis


def set_redis(client: Redis | None) -> None:
    """Для тестов: подменить клиент или отключить Redis."""
    global _redis
    _redis = client


async def read_generation(event_id: int) -> str | None:
    """Снимок generation до чтения БД. None - Redis недоступен."""
    client = _redis
    if client is None:
        return None
    try:
        raw = await client.get(_gen_key(event_id))
        return raw if raw is not None else "0"
    except RedisError:
        logger.warning("Redis get generation failed for event %s", event_id)
        return None


async def get_cached_availability(event_id: int) -> int | None:
    client = _redis
    if client is None:
        return None
    try:
        raw = await client.get(_value_key(event_id))
        if raw is None:
            return None
        gen_s, _, val_s = raw.partition(":")
        if not val_s:
            return None
        current_gen = await client.get(_gen_key(event_id))
        if current_gen is None:
            current_gen = "0"
        if gen_s != current_gen:
            return None
        return int(val_s)
    except (RedisError, ValueError, TypeError):
        logger.warning("Redis get availability failed for event %s", event_id)
        return None


async def set_cached_availability(
    event_id: int, available: int, generation: str | None
) -> bool:
    """Записать кэш только если generation не сменился. False - пропуск/ошибка."""
    if generation is None:
        return False
    client = _redis
    if client is None:
        return False
    settings = get_settings()
    try:
        current = await client.get(_gen_key(event_id))
        if current is None:
            current = "0"
        if current != generation:
            return False
        await client.set(
            _value_key(event_id),
            f"{generation}:{available}",
            ex=settings.availability_cache_ttl_seconds,
        )
        return True
    except RedisError:
        logger.warning("Redis set availability failed for event %s", event_id)
        return False


async def invalidate_availability(event_id: int) -> None:
    client = _redis
    if client is None:
        return
    try:
        pipe = client.pipeline(transaction=True)
        pipe.incr(_gen_key(event_id))
        pipe.delete(_value_key(event_id))
        await pipe.execute()
    except RedisError:
        logger.warning("Redis invalidate failed for event %s", event_id)
