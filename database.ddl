-- мероприятие
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    capacity INT NOT NULL DEFAULT 100,
    CHECK (capacity >= 0)
);

-- гости
CREATE TABLE users (
    id SERIAL PRIMARY KEY
);

-- бронирования
CREATE TABLE bookings (
    id SERIAL PRIMARY KEY,
    dedup_id INT NOT NULL,
    user_id INT NOT NULL REFERENCES users(id),
    event_id INT NOT NULL REFERENCES events(id),
    count INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    cancelled_at TIMESTAMP,
    confirmed BOOL NOT NULL DEFAULT FALSE,
    CHECK (count >= 1 AND count <= 5)
);

-- уникальность user + idempotency key
CREATE UNIQUE INDEX user_dedup_idx ON bookings (user_id, dedup_id);