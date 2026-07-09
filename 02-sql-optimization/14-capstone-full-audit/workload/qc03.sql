-- qc03: inventory corrections audit
-- Business: the ops "shrinkage & corrections" report lists, for the last 30
--           days, which products had the most manual inventory corrections
--           and the net quantity adjustment those corrections made.
-- Screaming: inventory control team -- this report used to be instant when
--           the events table was small; now it's the slowest tile on their
--           dashboard and keeps getting slower as more history accumulates.
-- SLA: p95 < 150 ms
SELECT product_id, count(*) AS correction_count, sum(qty_delta) AS net_delta
FROM inventory_events
WHERE event_type = 'correction'
  AND occurred_at >= now() - interval '30 days'
GROUP BY product_id
ORDER BY correction_count DESC
LIMIT 50;
