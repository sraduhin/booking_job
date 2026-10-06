-- Получить количество мест по event_id
SELECT capacity - booked FROM events WHERE id = $event_id;

-- Забронировать нужно количество мест
BEGIN;
    -- тут можем упасть по event_user_dedup_idx
    INSERT INTO bookings (event_id, user_id, dedup_id, count)
    VALUES ($event_id, $user_id, $dedup_id, $count);

    -- тут можем упасть по нарушению booked <= capacity
    UPDATE events SET booked = booked + $count WHERE id = $event_id;
COMMIT;

-- Подтвердить бронь
UPDATE bookings SET confirmed = true WHERE id = $booking_id;

-- Снять бронь по booking_id
BEGIN;
    UPDATE bookings SET cancelled_at NOW() WHERE id = $booking_id AND cancelled_at IS NULL;
    RETURNING count as recently_booked;
    UPDATE events SET booked = booked - $recently_booked WHERE id = $event_id;
COMMIT;