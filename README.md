# booking_job
Пет фо фан

## Запуск (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000/docs  
Postgres снаружи: `localhost:25432`

При старте `api` сам прогоняет миграции и при необходимости сиды.

Полный сброс данных:

```bash
docker compose down && rm -rf ../.db_data/bookings/postgres && docker compose up --build
```

## Debug (pydevd_pycharm)

1. В PyCharm: **Run → Edit Configurations → + → Python Debug Server**
   - IDE host name: `localhost`
   - Port: `5678` (как `DEBUG_PORT`)
2. Path mappings: контейнер `/app` → локальный корень репозитория
3. Версия пакета `pydevd-pycharm` должна совпадать с версией PyCharm (`Help → About`)
4. Запусти Debug Server в IDE, затем:

```bash
DEBUG=true docker compose up --build api
```

При `DEBUG=true` приложение при старте подключается к IDE через `DEBUG_HOST` (`host.docker.internal` из контейнера).

Заголовки: `X-User-Id`, для создания брони ещё `Dedup-Id` (INT).
