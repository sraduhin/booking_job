-- Получить количество мест по event_id
SELECT capacity - booked FROM events WHERE id = $event_id;

-- Забронировать нужно количество мест
BEGIN;
    -- тут можем упасть по user_dedup_idx
    INSERT INTO bookings (event_id, user_id, dedup_id, count)
    VALUES ($event_id, $user_id, $dedup_id, $count);

    -- тут можем упасть по нарушению booked <= capacity
    UPDATE events SET booked = booked + $count WHERE id = $event_id;
COMMIT;

-- Подтвердить бронь
UPDATE bookings SET confirmed = true
WHERE id = $booking_id
  AND cancelled_at IS NULL
  AND created_at > NOW() - INTERVAL '10 minutes';

-- Снять бронь по booking_id
BEGIN;
    UPDATE bookings SET cancelled_at = NOW() WHERE id = $booking_id AND cancelled_at IS NULL and confirmed = false
    RETURNING count AS recently_booked, event_id;
    UPDATE events SET booked = booked - $recently_booked WHERE id = $event_id;
COMMIT;