-- мероприятие
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    capacity INT NOT NULL DEFAULT 100,
    booked INT NOT NULL DEFAULT 0,
    -- ограничения
    CHECK (booked <= capacity AND booked >= 0 AND capacity >= 0)
);

-- гости
CREATE TABLE users (
    id SERIAL PRIMARY KEY
);

-- бронирования
CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    dedup_id INT NOT NULL,
    user_id INT REFERENCES users(id),
    event_id INT REFERENCES events(id),
    count INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    cancelled_at TIMESTAMP,
    confirmed BOOL NOT NULL DEFAULT FALSE
);

-- уникальность user + idempotency key
CREATE UNIQUE INDEX event_user_dedup_idx ON bookings (event_id, user_id, dedup_id);