Rough shape of the loop body for design (a), once `event = json.loads(msg.value())`:

```python
cur = conn.cursor()
cur.execute(
    "INSERT INTO ops.t04_seen (seq) VALUES (%s) ON CONFLICT DO NOTHING",
    (event["seq"],),
)
if cur.rowcount == 1:
    cur.execute(
        """
        INSERT INTO core.t04_category_totals (category, cnt, price_sum)
        VALUES (%s, 1, %s)
        ON CONFLICT (category) DO UPDATE SET
            cnt = core.t04_category_totals.cnt + 1,
            price_sum = core.t04_category_totals.price_sum + EXCLUDED.price_sum
        """,
        (event["category"], event["price"]),
    )
conn.commit()

processed += 1
_maybe_crash(processed)
consumer.commit(msg)
```

The crash hook sits AFTER `conn.commit()` and BEFORE `consumer.commit(msg)`
on purpose -- that's the exact window task 02 taught you is unavoidable
under at-least-once. On restart, the redelivered message runs the same
`INSERT ... ON CONFLICT DO NOTHING` against `ops.t04_seen`, finds its
`seq` already there, `cur.rowcount` is `0`, and the category-totals delta
is skipped. The aggregate is unaffected by however many times that message
gets redelivered after its first successful commit.

Design (b) looks almost the same, minus the `ops.t04_seen` check --
instead the same transaction always writes the offset row (upsert on
`(topic, partition)`), and correctness comes entirely from `on_assign`
seeking to `stored_offset + 1` on startup instead of trusting Kafka's own
committed offset.

Whichever design you pick, don't forget `ensure_core_table` only creates
`core.t04_category_totals` -- you're responsible for creating your own
`ops.t04_*` table (dedup or offsets) with `CREATE TABLE IF NOT EXISTS ...`
somewhere before the loop starts, same idempotent-create pattern.
