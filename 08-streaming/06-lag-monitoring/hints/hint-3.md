Rough shape of the loop body, once you're inside `main()` after
`ensure_ops_tables(conn)`:

```python
high = end_offsets(TOPIC)
committed = committed_offsets(GROUP_ID, TOPIC)

cur = conn.cursor()
snapshot_id = next_snapshot_id(conn)

total_lag = 0
for partition in sorted(high.keys()):
    h = high[partition]
    c = committed.get(partition, -1)
    lag = h if c < 0 else max(h - c, 0)
    total_lag += lag
    cur.execute(
        """
        INSERT INTO ops.t06_lag_snapshots
            (snapshot_id, topic, group_id, partition,
             high_watermark, committed_offset, lag)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (snapshot_id, TOPIC, GROUP_ID, partition, h, c, lag),
    )

threshold = lag_threshold()
if total_lag > threshold:
    cur.execute(
        "INSERT INTO ops.t06_alerts (snapshot_id, total_lag, threshold) "
        "VALUES (%s, %s, %s)",
        (snapshot_id, total_lag, threshold),
    )

conn.commit()
```

Notice `next_snapshot_id(conn)` is called with the *same* `conn` you're
about to insert into and haven't committed yet — reading `MAX(snapshot_id)
+ 1` before any of this run's rows exist is exactly what makes it safe to
call before the loop, inside the same transaction as the inserts that
follow. There's no concurrent second monitor process to race against in
this task, so you don't need `SELECT ... FOR UPDATE` or a sequence — the
plain `MAX + 1` read is enough.

Don't forget `conn.close()` isn't reached if you `raise NotImplementedError`
first — once you delete that line, make sure the function still ends with
`conn.commit()` before returning (a bare `close()` without a preceding
`commit()` would discard everything you just inserted).
