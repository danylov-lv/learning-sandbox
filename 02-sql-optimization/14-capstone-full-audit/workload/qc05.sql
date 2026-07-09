-- qc05: stuck-in-processing count
-- Business: an ops alert tile: how many orders have sat in "processing" for
--           up to two weeks, and what's their average value -- feeds a
--           paging threshold, so it runs every few minutes.
-- Screaming: on-call -- the tile itself has started showing up in the
--           slow-query log it was built to help monitor.
-- SLA: p95 < 40 ms
SELECT count(*) AS stuck_count, avg(total_amount) AS avg_amount
FROM orders
WHERE status = 'processing'
  AND created_at >= now() - interval '14 days';
