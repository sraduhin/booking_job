#!/usr/bin/env sh
set -e

echo "Running alembic upgrade head..."
alembic upgrade head

echo "Seeding if empty..."
python scripts/seed_if_empty.py

exec "$@"
