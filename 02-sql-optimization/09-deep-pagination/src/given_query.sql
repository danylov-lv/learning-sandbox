-- inventory event feed: deep page, newest-first
-- Business: the admin UI "inventory event feed" pages through all events
--           ordered newest-first with OFFSET/LIMIT. Shallow pages are fine;
--           support staff jumping to old pages (deep OFFSET) time out.
-- Screaming: support lead -- "page 8001 of the event feed just times out,
--           and staff need to get there to investigate an old ticket."
--
-- This file is GIVEN -- it is not yours to write or modify. It is the
-- query your keyset rewrite (src/page_query.sql) must reproduce the
-- results of, for the same logical page.
--
-- occurred_at has ties (many events share the same second), hence the
-- id DESC tie-break -- without it, "page N" would not be a well-defined,
-- stable set of rows across repeated OFFSET queries.
SELECT id, product_id, event_type, qty_delta, occurred_at
FROM inventory_events
ORDER BY occurred_at DESC, id DESC
OFFSET 800000 LIMIT 100;
