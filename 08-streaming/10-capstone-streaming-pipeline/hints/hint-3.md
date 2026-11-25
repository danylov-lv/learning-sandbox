# Hint 3

Rough shape of the loop body in `src/pipeline.py`, once
`event = json.loads(msg.value())`:

```python
cur = conn.cursor()
cur.execute(
    "INSERT INTO ops.t10_seen (seq) VALUES (%s) ON CONFLICT DO NOTHING",
    (event["seq"],),
)
if cur.rowcount == 1:
    cur.execute(
        """
        INSERT INTO core.t10_latest_price
            (product_id, price, currency, in_stock, event_ts, seq)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (product_id) DO UPDATE SET
            price = EXCLUDED.price,
            currency = EXCLUDED.currency,
            in_stock = EXCLUDED.in_stock,
            event_ts = EXCLUDED.event_ts,
            seq = EXCLUDED.seq
        WHERE EXCLUDED.seq > core.t10_latest_price.seq
        """,
        (event["product_id"], event["price"], event["currency"],
         event["in_stock"], event["event_ts"], event["seq"]),
    )

    cur.execute(
        """
        INSERT INTO mart.t10_category_totals (category, cnt, price_sum)
        VALUES (%s, 1, %s)
        ON CONFLICT (category) DO UPDATE SET
            cnt = mart.t10_category_totals.cnt + 1,
            price_sum = mart.t10_category_totals.price_sum + EXCLUDED.price_sum
        """,
        (event["category"], event["price"]),
    )

    window_start = window_start_for(event["event_ts"])
    cur.execute(
        """
        INSERT INTO mart.t10_window_category (window_start, category, cnt, price_sum)
        VALUES (%s, %s, 1, %s)
        ON CONFLICT (window_start, category) DO UPDATE SET
            cnt = mart.t10_window_category.cnt + 1,
            price_sum = mart.t10_window_category.price_sum + EXCLUDED.price_sum
        """,
        (window_start, event["category"], event["price"]),
    )

conn.commit()

processed += 1
_maybe_crash(processed)
consumer.commit(msg)
```

Note the insert order: `ops.t10_seen` first (the gate), then
`core.t10_latest_price` (per-key, never contended across instances since a
product's partition never moves within one rebalance-free stretch), then
the two shared `mart.*` tables last. Every transaction touching these four
tables in this repo uses that same order — that consistent ordering is
what keeps two concurrent instances from ever deadlocking against each
other on Postgres row locks, even though `mart.t10_category_totals` and
`mart.t10_window_category` rows are genuinely shared and contended.

For `src/monitor.py`, the loop is a straight port of task 06's monitor
minus the alert table:

```python
high = end_offsets(TOPIC)
committed = committed_offsets(GROUP_ID, TOPIC)
snapshot_id = next_snapshot_id(conn)

cur = conn.cursor()
for p in sorted(high.keys()):
    committed_offset = committed.get(p, -1)
    lag = high[p] if committed_offset < 0 else high[p] - committed_offset
    lag = max(lag, 0)
    cur.execute(
        "INSERT INTO ops.t10_lag_snapshots "
        "(snapshot_id, topic, group_id, partition, high_watermark, committed_offset, lag) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (snapshot_id, TOPIC, GROUP_ID, p, high[p], committed_offset, lag),
    )
conn.commit()
```

## Making 200k events fast (throughput, not a pass/fail gate)

The four-separate-`cur.execute` shape above is ~5 Postgres round trips per
message (one dedup insert, three upserts, one commit). Over 200k events
that is a million round trips -- correct, and it will pass within the
validator's generous timeout, but slow, and real streaming pipelines don't
commit per row like that. Two changes make it much faster, neither of which
weakens correctness:

1. `cur.execute("SET synchronous_commit TO off")` once, right after you open
   the connection. Your per-message commit no longer waits for an fsync.
   This is safe here specifically because the crash hook is a *process*
   crash (`os._exit`), not a server/OS crash -- the committed rows are
   already durable in the still-running Postgres server, and even if they
   weren't, the Kafka offset for those messages was never committed, so
   redelivery would reapply them and `ops.t10_seen` would make that a
   no-op.
2. Collapse the dedup gate and all three effects into ONE statement with a
   writeable CTE, so it's a single round trip per message:

   ```sql
   WITH ins AS (
       INSERT INTO ops.t10_seen (seq) VALUES (%(seq)s)
       ON CONFLICT DO NOTHING RETURNING seq
   ), lp AS (
       INSERT INTO core.t10_latest_price
           (product_id, price, currency, in_stock, event_ts, seq)
       SELECT %(product_id)s, %(price)s, %(currency)s, %(in_stock)s,
              %(event_ts)s, %(seq)s
       FROM ins
       ON CONFLICT (product_id) DO UPDATE SET
           price = EXCLUDED.price, currency = EXCLUDED.currency,
           in_stock = EXCLUDED.in_stock, event_ts = EXCLUDED.event_ts,
           seq = EXCLUDED.seq
       WHERE EXCLUDED.seq > core.t10_latest_price.seq
   ), ct AS (
       INSERT INTO mart.t10_category_totals (category, cnt, price_sum)
       SELECT %(category)s, 1, %(price)s FROM ins
       ON CONFLICT (category) DO UPDATE SET
           cnt = mart.t10_category_totals.cnt + 1,
           price_sum = mart.t10_category_totals.price_sum + EXCLUDED.price_sum
   )
   INSERT INTO mart.t10_window_category (window_start, category, cnt, price_sum)
   SELECT %(window_start)s, %(category)s, 1, %(price)s FROM ins
   ON CONFLICT (window_start, category) DO UPDATE SET
       cnt = mart.t10_window_category.cnt + 1,
       price_sum = mart.t10_window_category.price_sum + EXCLUDED.price_sum
   ```

   Each downstream `INSERT ... SELECT ... FROM ins` runs only when `ins`
   actually inserted (seq is new) -- `ins` returns one row on first sight,
   zero rows on a redelivery, so a replayed message drives zero downstream
   writes. This IS the dedup gate, expressed as one statement instead of an
   `if cur.rowcount == 1:` around four. Bind the params by name (a dict)
   since `%(seq)s` appears more than once.

   If you'd rather keep the readable four-statement version, the other way
   to cut the cost is to batch commits (task 05's advice) -- but then keep
   per-batch transactions SHORT and be aware that two concurrent instances
   holding many mart row locks across a long batch can deadlock on the hot
   category/window rows; per-message commit (with `synchronous_commit off`)
   sidesteps that entirely by releasing locks immediately.

If CP2 shows drift after the crash+rebalance phase but CP1 alone passes,
the bug is almost always one of: (a) the Kafka offset commit landing
before, not after, `_maybe_crash`/the Postgres commit; (b) a per-effect
dedup table instead of one shared gate, letting some effects apply twice
while others don't; or (c) missing the `WHERE EXCLUDED.seq > ...` guard
on `core.t10_latest_price`, which a single-instance CP1 run would never
expose (nothing ever redelivers out of seq order there) but a rebalance
mid-stream can.
