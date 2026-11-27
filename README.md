# booking_job
Пет фо фан

## Запуск (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

API: http://localhost:8000/docs  
Postgres снаружи: `localhost:25432`  
Redis снаружи: `localhost:26379`

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
DEBUG=true docker compose up api
```

При `DEBUG=true` приложение при старте подключается к IDE через `DEBUG_HOST` (`host.docker.internal` из контейнера).

Заголовки: `X-User-Id`, для создания брони ещё `Dedup-Id` (INT).

Авторизацию осознанно не делаю. Была пробная попытка перейти на JWT Bearer, но много что за этим тянется:
 - ручной seed сломал sequence. Плюс менее наглядный механизм самого seed.
 - задача совсем не про auth

## Redis-кэш availability

`GET /events/{id}/availability` кэширует число свободных мест в Redis (TTL по умолчанию 10 с).

Гарантии свежести:
- TTL записи - максимум, сколько ответ GET может жить в Redis после записи.
- после `POST /bookings` и `POST /bookings/{id}/cancel` ключ удаляется сразу после коммита в PostgreSQL.
- GET может отдать устаревшее значение в пределах TTL, однако создание брони **всегда** считает занятость в PostgreSQL внутри транзакции с `FOR UPDATE` по мероприятию - устаревший кэш не даёт забронировать лишнее.
- Если Redis недоступен или ошибка при get/set/invalidate - читаем/пишем БД как обычно; операции с бронями не падают.

При обновлении кеша читаем текущее значение плюс generation и записываем в кэш. Инвалидация кэша инкрементирует generation. При влезшей инвалидации в процесс обновления, запись не применится, тк проверяется соответствие текущего generation и записываемого (старого).

## Тесты

Нужны Postgres и Redis из compose (`localhost:25432`, `localhost:26379`). Тесты сами создают БД `booking_test`, накатывают миграции и используют Redis DB `15`.

```bash
docker compose up -d db redis
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```
