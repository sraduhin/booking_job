"""initial schema from database.ddl

Revision ID: 001
Revises: 
Create Date: 2026-11-09 17:13:50.598749

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DDL_PATH = Path(__file__).resolve().parents[2] / "database.ddl"


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


def upgrade() -> None:
    conn = op.get_bind()
    for statement in _statements(DDL_PATH.read_text(encoding="utf-8")):
        conn.execute(text(statement))


def downgrade() -> None:
    op.execute(text("DROP TABLE IF EXISTS bookings"))
    op.execute(text("DROP TABLE IF EXISTS users"))
    op.execute(text("DROP TABLE IF EXISTS events"))
