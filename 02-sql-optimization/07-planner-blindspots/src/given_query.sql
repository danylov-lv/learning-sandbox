-- ops fulfillment queue: orders stuck in "processing"
-- Business: warehouse ops pulls this list every morning to chase down
--           orders that have been sitting in "processing" too long, with
--           customer contact info attached for follow-up calls.
-- Screaming: ops lead — the queue view now takes so long to load that
--           agents have started refreshing mid-load and giving up.
-- SLA: p95 < 40 ms
--
-- This file is GIVEN — it is not yours to write or modify. Your task is to
-- fix why the planner picks a bad plan for it, not to rewrite the query.
SELECT o.id, o.created_at, o.total_amount, u.email, u.full_name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'processing'
  AND o.created_at >= now() - interval '30 days'
ORDER BY o.created_at
LIMIT 200;
