-- qc08: seller revenue leaderboard (last 6 hours)
-- Business: the seller-ops dashboard refreshes a "who's selling right now"
--           leaderboard every few hours, ranking sellers by revenue booked
--           across their products' most recent order line items.
-- Screaming: seller-ops -- the leaderboard tile times out on refresh often
--           enough that the team has started ignoring it, defeating the
--           point of a live dashboard.
-- SLA: p95 < 50 ms
SELECT s.name AS seller_name, sum(oi.quantity * oi.unit_price) AS revenue_recent
FROM sellers s
JOIN products p ON p.seller_id = s.id
JOIN order_items oi ON oi.product_id = p.id
JOIN orders o ON o.id = oi.order_id
WHERE o.created_at >= now() - interval '6 hours'
GROUP BY s.name
ORDER BY revenue_recent DESC
LIMIT 20;
