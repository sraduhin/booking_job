"""Применяет seed.sql один раз, если в events ещё нет строк."""

from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

SEED_PATH = Path(__file__).resolve().parents[1] / "seed.sql"


def _statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buf).strip().rstrip(";").strip()
            if statement:
                parts.append(statement)
            buf = []
    if buf:
        statement = "\n".join(buf).strip().rstrip(";").strip()
        if statement:
            parts.append(statement)
    return parts


async def main() -> None:
    if not SEED_PATH.is_file():
        return

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            count = (
                await conn.execute(text("SELECT COUNT(*) FROM events"))
            ).scalar_one()
            if count:
                return
            for statement in _statements(SEED_PATH.read_text(encoding="utf-8")):
                await conn.execute(text(statement))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
