-- Task 09: deep pagination -- keyset ("cursor") rewrite.
--
-- Must return the SAME rows as src/given_query.sql's deep page, but without
-- an OFFSET. Parameterized with psycopg named placeholders:
--   %(cursor_occurred_at)s  -- occurred_at of the last row of the PREVIOUS page
--   %(cursor_id)s           -- id of that same last row (tie-break)
--
-- Contract: the caller always supplies the (occurred_at, id) pair of the
-- last row it received on the previous page. For the very first page there
-- is no previous row -- that case is not exercised by this task's checker,
-- which always supplies a real cursor from a known previous page.
--
-- Write a WHERE clause that walks the (occurred_at, id) ordering forward
-- from that cursor, in the same DESC, DESC order as the given query, then
-- LIMIT 100. No OFFSET anywhere in your query.
--
-- TODO: replace this stub with your keyset query.
SELECT id, product_id, event_type, qty_delta, occurred_at
FROM inventory_events
WHERE false
LIMIT 100;
