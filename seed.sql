-- одно мероприятие на 10 мест
INSERT INTO events (capacity) VALUES (10);

-- 100 гостей
INSERT INTO users (id)
SELECT n FROM generate_series(1, 100) AS n;
