Concretely:

```python
high = end_offsets(TOPIC)              # {0: 4123, 1: 4098, ...}
committed = committed_offsets(GROUP_ID, TOPIC)  # {0: 4123, 1: -1, ...}
```

Iterate over `high`'s partitions (that's the authoritative partition set —
`committed_offsets` returns the same keys, but don't assume the two dicts
necessarily agree on which partitions exist if you ever point this at a
topic that changed partition count between calls). For each partition:

```python
c = committed.get(partition, -1)
lag = high[partition] if c < 0 else high[partition] - c
lag = max(lag, 0)
```

Sort partitions before inserting rows (`sorted(high.keys())`) — not
required for correctness, but it makes the table readable and matches how
the validator reads rows back for comparison.

For the snapshot id: call `next_snapshot_id(conn)` exactly once at the top
of the snapshot, before you start inserting rows, and reuse that same
value for every row (including the alert row, if you raise one). Calling
it more than once per run — or computing it per-partition — would give
each row a different snapshot_id, which breaks "one snapshot = one
snapshot_id."

For the alert: compute `total_lag = sum(...)` only after you've computed
every partition's lag, compare against `lag_threshold()`, and insert into
`ops.t06_alerts` only on the `>` branch (strictly greater — a snapshot
exactly at the threshold should not alert, per the table contract).
