Debezium's Postgres connector uses `pgoutput` against a publication that
covers `shop.offers` as a whole table, not a fixed list of columns pinned
at connector-registration time. When the source runs `ALTER TABLE
shop.offers ADD COLUMN discount_pct NUMERIC(5,2)`, the very next
insert/update on that table just has one more field in its logical-decode
output, and Debezium republishes that as one more key in `after`. There is
no separate "schema changed" event you need to catch or branch on for an
additive change like this -- the DDL itself needs no special handling.

So the fix lives entirely on the read side: build `replica.offers` with
the new column present (nullable) from the start, and read every field out
of `after` with `.get(field)` instead of `after[field]`. A `None` back
from `.get("discount_pct")` just means "this particular event predates the
column" -- treat it the same as any other legitimately-NULL value, not as
an error.

Keep the write side (your `INSERT ... ON CONFLICT DO UPDATE`) uniform
across both event shapes -- don't branch your SQL on "does this after-image
have discount_pct or not." A NULL is a perfectly normal value to upsert.
