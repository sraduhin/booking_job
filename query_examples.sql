-- Получить количество свободных мест по event_id.
SELECT e.capacity - COALESCE((
    SELECT SUM(b.count)
    FROM bookings b
    WHERE b.event_id = e.id
      AND b.cancelled_at IS NULL
      AND (b.confirmed = true OR b.created_at > clock_timestamp() - INTERVAL '10 minutes')
), 0)
FROM events e
WHERE e.id = $event_id;

-- Забронировать нужно количество мест.
BEGIN;
    SELECT capacity FROM events WHERE id = $event_id FOR UPDATE;

    INSERT INTO bookings (event_id, user_id, dedup_id, count)
    SELECT $event_id, $user_id, $dedup_id, $count
    WHERE (
        SELECT COALESCE(SUM(count), 0)
        FROM bookings
        WHERE event_id = $event_id
          AND cancelled_at IS NULL
          AND (confirmed = true OR created_at > clock_timestamp() - INTERVAL '10 minutes')
    ) + $count <= (SELECT capacity FROM events WHERE id = $event_id);
COMMIT;

-- Подтвердить бронь.
BEGIN;
    SELECT created_at, cancelled_at, confirmed
    FROM bookings
    WHERE id = $booking_id
    FOR UPDATE;

    UPDATE bookings SET confirmed = true
    WHERE id = $booking_id
      AND cancelled_at IS NULL
      AND confirmed = false
      AND created_at > clock_timestamp() - INTERVAL '10 minutes';
COMMIT;

-- Снять бронь по booking_id.
UPDATE bookings SET cancelled_at = clock_timestamp()
WHERE id = $booking_id
  AND cancelled_at IS NULL
  AND confirmed = false;
