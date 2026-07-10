# Hint 2

Concrete SQL for each of the four effects, once you know whether this
event's `seq` is new:

```sql
-- 1. the gate
INSERT INTO ops.t10_seen (seq) VALUES (%s) ON CONFLICT DO NOTHING;
-- cur.rowcount == 1 means this seq has never been applied before.
```

If (and only if) that insert actually happened:

```sql
-- 2. category totals
INSERT INTO mart.t10_category_totals (category, cnt, price_sum)
VALUES (%s, 1, %s)
ON CONFLICT (category) DO UPDATE SET
    cnt = mart.t10_category_totals.cnt + 1,
    price_sum = mart.t10_category_totals.price_sum + EXCLUDED.price_sum;

-- 3. window/category totals (window_start computed in Python via
-- window_start_for(event["event_ts"]), already given)
INSERT INTO mart.t10_window_category (window_start, category, cnt, price_sum)
VALUES (%s, %s, 1, %s)
ON CONFLICT (window_start, category) DO UPDATE SET
    cnt = mart.t10_window_category.cnt + 1,
    price_sum = mart.t10_window_category.price_sum + EXCLUDED.price_sum;

-- 4. latest price, last-write-wins by seq
INSERT INTO core.t10_latest_price (product_id, price, currency, in_stock, event_ts, seq)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (product_id) DO UPDATE SET
    price = EXCLUDED.price,
    currency = EXCLUDED.currency,
    in_stock = EXCLUDED.in_stock,
    event_ts = EXCLUDED.event_ts,
    seq = EXCLUDED.seq
WHERE EXCLUDED.seq > core.t10_latest_price.seq;
```

The `WHERE EXCLUDED.seq > ...` clause on step 4 is the whole "guarded so
re-applying an older seq never regresses" requirement — without it, an
`ON CONFLICT DO UPDATE` always fires, and a topic re-read from scratch (or
a genuinely out-of-order redelivery) could overwrite a newer row with a
stale one even though `ops.t10_seen` already deduped the *event itself*
correctly. `ops.t10_seen` guarantees each event is applied at most once;
the `WHERE` clause on step 4 guarantees the *order* those applications
land in doesn't matter for this particular table. You don't need an
equivalent guard on steps 2/3 — `cnt += 1` / `price_sum += price` are
commutative, order never matters for a running sum.

For the rebalance test specifically: launching two `pipeline.py`
processes with plain `subprocess.Popen` (not `run`) and calling
`.communicate()` on each afterward is enough to get them running
concurrently — you don't need any special orchestration in the pipeline
script itself for this to work, provided the four-effects-behind-one-gate
design above is right.
