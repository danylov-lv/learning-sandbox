Design (a), idempotent dedup, concretely:

```sql
CREATE TABLE IF NOT EXISTS ops.t04_seen (seq BIGINT PRIMARY KEY);
```

Per message, in one transaction:

```sql
INSERT INTO ops.t04_seen (seq) VALUES (%s) ON CONFLICT DO NOTHING;
```

Check `cur.rowcount` (or use `... ON CONFLICT DO NOTHING RETURNING seq` and
check whether `fetchone()` returned anything) to know whether this exact
insert actually happened. If it did, this is the first time you've ever
seen this `seq` -- apply the category-totals delta in the SAME
transaction. If it didn't (conflict), you've applied this event's delta
before; skip the delta but still `conn.commit()` -- committing an empty
no-op is fine, it just has to happen so the loop keeps moving.

Design (b), transactional offset storage, concretely:

```sql
CREATE TABLE IF NOT EXISTS ops.t04_offsets (
    topic TEXT NOT NULL, partition INT NOT NULL, "offset" BIGINT NOT NULL,
    PRIMARY KEY (topic, partition)
);
```

Per message, in one transaction: upsert the category-totals delta AND
upsert `(TOPIC, msg.partition())` -> `msg.offset()` into `ops.t04_offsets`,
then commit once. On startup (`on_assign`), for each partition, `SELECT
"offset" FROM ops.t04_offsets WHERE topic=%s AND partition=%s`; if a row
exists, `p.offset = stored + 1` before `consumer.assign(partitions)`; if
no row, leave `p.offset` alone (falls back to `auto.offset.reset`). Notice
this design never needs to check "have I seen this seq" at all -- the
offset IS the checkpoint, and because it moves in the same transaction as
the aggregate, replaying from a stale offset after a crash re-applies
exactly the deltas that never committed, and nothing else.

Either design: the category-totals upsert itself needs `ON CONFLICT
(category) DO UPDATE SET cnt = t04_category_totals.cnt + 1, price_sum =
t04_category_totals.price_sum + EXCLUDED.price_sum` (seeded via an
`INSERT ... VALUES (category, 1, price)` on the no-conflict branch).
