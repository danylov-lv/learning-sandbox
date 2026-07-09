-- q02: support dashboard customer summary
-- Business: support agents open this per-customer panel on every ticket:
--           order count and total spend over the last 90 days.
-- Screaming: support leads — agents wait 10+ seconds per ticket.
-- SLA: p95 < 100 ms
SELECT count(*) AS orders_90d,
       COALESCE(sum(total_amount), 0) AS spend_90d,
       max(created_at) AS last_order_at
FROM orders
WHERE user_id = 42
  AND created_at >= now() - interval '90 days';
