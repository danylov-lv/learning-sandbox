# 10 — Partition the Firehose

## Backstory

`inventory_events` is an append-heavy time series: every stock movement in
the warehouse writes a row here, and it has grown to 9.0M rows spanning
January 2025 through today. Every ops query filters a recent window
("what happened in the last two weeks"), but the table itself doesn't know
that — it's one flat heap with two single-column indexes. Monthly
retention jobs `DELETE` old rows to keep the table from growing forever,
and those deletes are slow, lock-contending, and leave bloat behind: the
table already carries 450,000 dead tuples from past retention runs. Ops
wants a design where "delete last month's data" is closer to instant and
"query the last two weeks" doesn't have to consult months of unrelated
rows in the process.

## What's given

- `seed/schema.sql` — the live schema (read-only reference; do not edit, do
  not run it against the DB). Read the comment on `inventory_events` —
  defect (c) is this task's subject.
- A live Postgres 16 instance at `localhost:54302` (db/user/pass:
  `sandbox`), container `02-sql-optimization-postgres-1`. `inventory_events`
  has 9.0M rows; `min(occurred_at)` is 2025-01-10, `max(occurred_at)` is
  today.
- `src/recent_window_query.sql` — the query used for the pruning and
  (informational) timing checks. Reference only, not yours to write.
- `tools/plan_check.py` and `tools/baseline.py` — the plan-assertion and
  timing-baseline helpers used by the checker.
- `src/migrate.sql` — stub. You write your migration here.

## What's required

1. First, look at the data yourself:
   `SELECT min(occurred_at), max(occurred_at), count(*) FROM
   inventory_events;` and a per-month breakdown
   (`date_trunc('month', occurred_at)`), so you know exactly what span your
   partitions need to cover.
2. Write `src/migrate.sql` as a single transactional script
   (`BEGIN; ... COMMIT;`, runnable with `psql ... -f src/migrate.sql` or any
   client that executes the whole file as one script) that:
   - creates a new table partitioned `BY RANGE (occurred_at)`, with one
     partition per calendar month, covering the full existing span **plus
     at least one wholly future month** (so the very next month's data
     already has somewhere to land without a DDL scramble);
   - moves all 9M existing rows into it;
   - ends with the partitioned table actually named `inventory_events`
     (swap the old table out of the way, rename the new one in) and with
     the indexes ops actually needs recreated on the partitioned table
     (indexes declared on a partitioned table are created automatically on
     every partition, current and future).
3. You may touch only `inventory_events`. Do not modify `products`, `orders`,
   `order_items`, `reviews`, `payments`, `users`, `sellers`, or `categories`
   in any way.
4. This is a heavy, minutes-long operation on 9M rows — run it once,
   deliberately, against the live DB. `tests/check.py` inspects whatever
   state you leave the table in; it does not run your migration for you and
   does not undo it.

## Completion criteria

Run, from the module root, after applying `src/migrate.sql` yourself:

```
uv run python 10-partition-the-firehose/tests/check.py
```

The checker verifies:

1. `inventory_events` is a partitioned table using the RANGE strategy.
2. There are enough partitions to plausibly cover the real span (at least
   20 — about 19 months of real data plus a future one), and at least one
   partition's lower bound is strictly after the stock table's
   `max(occurred_at)` — proof you actually planned ahead, not just for
   what exists today.
3. Data parity: `count(*)`, `sum(qty_delta)`, `min(occurred_at)`, and
   `max(occurred_at)` on the migrated table match the stock values exactly.
   No rows lost, duplicated, or corrupted in the move.
4. A last-14-days query (`src/recent_window_query.sql`) touches at most 2
   partitions — proof the planner is pruning, not scanning every month.

A timing comparison against a stock baseline is also printed, but as
`info` only, not a pass/fail gate — see "Topics to read up on" for why a
single small recent-window query isn't necessarily dramatically faster
just from partitioning alone, when the unpartitioned table already had an
index on `occurred_at`. The pruning and structural checks are the real
signal for this task.

All checks except the timing line must print `PASS`, and the final line
must read `PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- Declarative partitioning in Postgres: `PARTITION BY RANGE`, partition
  bounds, and the `DEFAULT` partition tradeoff
- Partition pruning: plan-time vs. run-time, and why an unbounded range
  filter (no upper bound) can defeat pruning against future partitions
  even when it works fine for a bounded window
- `DETACH PARTITION` / `DROP TABLE` as O(1) alternatives to a row-by-row
  `DELETE` for retention
- Why partitioned-table indexes are declared once but built once per
  partition
- Online partitioning migration strategies (logical replication,
  trigger-based dual writes, `pg_partman`) as alternatives to a
  single-transaction copy-and-swap, and what a single-transaction swap
  costs you (lock duration, disk for the temporary duplicate) that those
  alternatives avoid

## A note on `.authoring/`

There's a design-notes file at the module root under `.authoring/` that
documents this and other tasks' intended defects and fixes, including how
the pruning and parity thresholds here were calibrated. It's off-limits
before you attempt this task — read it afterward if you're curious.
