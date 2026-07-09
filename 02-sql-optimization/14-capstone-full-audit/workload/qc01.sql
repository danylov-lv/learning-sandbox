-- qc01: order history tab, filtered by status
-- Business: the account page's "Delivered & Shipped" tab lists a customer's
--           orders in those two statuses, newest first.
-- Screaming: mobile team again -- this tab is slower than the plain "all
--           orders" list they already fixed elsewhere, because it still has
--           nowhere to go but a full scan for one customer's rows.
-- SLA: p95 < 50 ms
SELECT id, status, total_amount, created_at
FROM orders
WHERE user_id = 2
  AND status IN ('delivered', 'shipped')
ORDER BY created_at DESC
LIMIT 50;
