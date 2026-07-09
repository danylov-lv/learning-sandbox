-- qc07: regional recent-orders feed
-- Business: the EU ops desk watches a live feed of recent orders from a
--           given country, with customer name and city attached, to spot
--           regional fulfillment problems as they happen.
-- Screaming: EU ops -- the feed lags so far behind that by the time an
--           order appears, the problem it would have flagged is already a
--           support ticket.
-- SLA: p95 < 50 ms
SELECT o.id, o.created_at, o.total_amount, u.full_name, u.city
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE u.country = 'DE'
  AND o.created_at >= now() - interval '7 days'
ORDER BY o.created_at DESC
LIMIT 100;
