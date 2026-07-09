-- q04: mobile order list (slim projection)
-- Business: the app's "My orders" screen needs only date, status and total
--           for the latest 25 orders — nothing else.
-- Screaming: mobile team — this is their single hottest endpoint.
-- SLA: p95 < 30 ms; ideally served from the index alone
SELECT created_at, status, total_amount
FROM orders
WHERE user_id = 42
  AND created_at >= now() - interval '365 days'
ORDER BY created_at DESC
LIMIT 25;
