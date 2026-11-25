`setup_topic.py`: `create_topic` returns `True` if it actually created the
topic and `False` if it already existed — use that for your print, don't
call `topic_exists` separately. For the compaction knobs: `segment.ms` in
milliseconds (something well under an hour, e.g. `"60000"` for one minute,
so a new segment rolls often enough during a short exploration session to
give the cleaner more than one segment to work with) and
`min.cleanable.dirty.ratio` as a string fraction well below the `0.5`
default (e.g. `"0.1"`) so the cleaner doesn't wait for half the log to be
garbage before it bothers compacting.

`upsert_latest`: the shape is

```sql
INSERT INTO core.t07_latest_price (product_id, price, currency, in_stock, event_ts, seq)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (product_id) DO UPDATE
SET price = EXCLUDED.price,
    currency = EXCLUDED.currency,
    in_stock = EXCLUDED.in_stock,
    event_ts = EXCLUDED.event_ts,
    seq = EXCLUDED.seq
WHERE EXCLUDED.seq > core.t07_latest_price.seq
```

`EXCLUDED` refers to the row that was proposed for insertion (i.e. the new
event). When the `WHERE` condition is false, Postgres does not raise an
error and does not insert a second row — it just leaves the existing row
untouched. That's the entire seq guard: no `if` statement in Python needed,
the database enforces it per-row.

For the event's `event_ts` field: it's already an ISO-8601 string with a
`Z` suffix (e.g. `"2025-07-01T00:37:12.123Z"`) — psycopg/Postgres will
parse that directly into `TIMESTAMPTZ` without you needing to touch
`datetime` at all.
