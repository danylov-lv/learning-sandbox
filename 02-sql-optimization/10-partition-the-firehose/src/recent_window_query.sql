-- Reference-only: the "recent window" query used by tests/check.py's
-- informational timing comparison and pruning check. Not something you
-- write -- provided so you can record the stock baseline with tools/baseline.py
-- before migrating, if you want the timing comparison to mean anything.
SELECT count(*) FROM inventory_events
WHERE occurred_at >= now() - interval '14 days' AND occurred_at <= now();
