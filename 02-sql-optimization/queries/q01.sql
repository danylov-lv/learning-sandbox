-- q01: user order history (account page)
-- Business: every account-page load lists the customer's 20 most recent orders.
-- Screaming: mobile team — account page spinner, App Store reviews mention it.
-- SLA: p95 < 50 ms
SELECT id, status, total_amount, created_at
FROM orders
WHERE user_id = 42
ORDER BY created_at DESC
LIMIT 20;
