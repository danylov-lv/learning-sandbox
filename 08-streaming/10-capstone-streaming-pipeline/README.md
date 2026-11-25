# 10 — Capstone: Streaming Pipeline

## Backstory

Tasks 01-07 each proved one concept in isolation: replay from offset zero
(task 01), survive a crash with zero loss (task 02), watch a rebalance
happen (task 03), turn at-least-once into an exactly-once aggregate (task
04), get event-time windowing right despite late events (task 05), watch
lag climb and alert on it (task 06), materialize last-write-wins state
from a compacted topic (task 07). Production doesn't run concepts. It runs
one pipeline, and that pipeline gets crashed on by accident, rebalanced by
a deploy, and paged on by whoever's on call — all in the same week, maybe
the same night.

This capstone is that pipeline. One consumer group, reading one live
price-update stream, folding it into three different kinds of state at
once — a running total per category, a per-category total *per 15-minute
event-time window*, and "what does this product cost right now" — while
staying exactly-once under a crash and staying correct under a rebalance,
the way a RabbitMQ competing-consumer setup never had to, because RMQ
deletes a message the moment it's acked and has no shared log a second
consumer can rejoin mid-stream. Here, the offset IS the shared bookmark,
and the group can gain or lose a member at any moment without anyone
losing or duplicating a single event's effect.

## What's given

- `src/pipeline.py` — the main scaffold:
  - DDL/`ensure_tables` for all four tables this pipeline maintains:
    `ops.t10_seen`, `mart.t10_category_totals`,
    `mart.t10_window_category`, `core.t10_latest_price` — already written,
    not the point of the exercise.
  - Constants: `TOPIC` (`s07.t10.price-updates`), `GROUP_ID`
    (`t10-pipeline`), `IDLE_EXIT_SECONDS`, `WINDOW_SECONDS` (900),
    `WINDOW_BASE` (`2025-07-01T00:00:00Z`).
  - `window_start_for` — task 05's window-flooring mechanic, already
    solved (this capstone is about composing four solved mechanics under
    stress, not re-deriving any one of them).
  - `_maybe_crash`, a **test hook** identical in spirit to task 04's: if
    `S07_CRASH_AFTER` is set, hard-exits the process the instant this
    run's processed-count reaches it. Call it once per message, after
    your Postgres transaction has committed and before the Kafka offset
    commit.
  - An `on_assign` stub (given as a plain `consumer.assign(partitions)` —
    the exactly-once design here doesn't need transactional offset
    storage; see the module docstring for why).
  - The poll loop skeleton. Stops with `raise NotImplementedError` at the
    one place that matters: applying a single event's effect on all four
    tables exactly once.
- `src/monitor.py` — a lighter version of task 06's lag monitor: takes one
  lag snapshot for group `t10-pipeline` into `ops.t10_lag_snapshots`, no
  alerting required. Same `raise NotImplementedError` shape as task 06.
- `src/DESIGN_TEMPLATE.md` — copy to this task's root as `DESIGN.md` for
  CP3.
- `tests/validate_cp1.py`, `tests/validate_cp2.py`, `tests/validate_cp3.py`
  — the validators.
- `hints/`, `NOTES.md`.

## What's required

Per message, inside **one** Postgres transaction:

1. Dedup on `seq` via `ops.t10_seen(seq BIGINT PRIMARY KEY)`,
   `INSERT ... ON CONFLICT DO NOTHING`; only apply the effects below when
   that insert actually inserted a new row (redelivery becomes a no-op —
   this is task 04's idempotent-dedup design, generalized to four effects
   instead of one).
2. `mart.t10_category_totals(category, cnt, price_sum)` — `cnt += 1`,
   `price_sum += price`.
3. `mart.t10_window_category(window_start, category, cnt, price_sum)` —
   `window_start` = `event_ts` floored to its 15-minute tumbling window
   (task 05's mechanic — use `event_ts`, never offset/arrival order; ~2%
   of events are late).
4. `core.t10_latest_price(product_id, price, currency, in_stock,
   event_ts, seq)` — last-write-wins by `seq` (publish order, task 07's
   lesson), guarded so re-applying an older `seq` never regresses a newer
   row.
5. Commit once. **Then** `processed += 1; _maybe_crash(processed);
   consumer.commit(msg)` — the Kafka offset commit is deliberately outside
   the atomic unit.

The whole thing must also tolerate **two concurrent `pipeline.py`
instances in the same consumer group** — a rebalance happens the instant
the second one joins. Per-key ordering means a given `product_id` always
lands in the same partition, so `core.t10_latest_price` never has a
cross-instance race; `mart.t10_category_totals` and
`mart.t10_window_category` are shared across partitions and serialize
through ordinary Postgres row locks on the upsert.

Try it by hand before trusting the validators:

```bash
uv run python src/pipeline.py                        # normal run, no crash
S07_CRASH_AFTER=60000 uv run python src/pipeline.py   # dies partway
uv run python src/pipeline.py                         # resumes and catches up
uv run python src/pipeline.py & uv run python src/pipeline.py & wait   # forced rebalance
uv run python src/monitor.py                          # one lag snapshot
```

## Checkpoints

### CP1 — steady pipeline

```bash
uv run python tests/validate_cp1.py
```

Resets the topic, produces the full corpus, drops all four tables, runs
`pipeline.py` once to completion, and checks `mart.t10_category_totals`,
`mart.t10_window_category`, and `core.t10_latest_price` against
`data/ground-truth.json` exactly.

### CP2 — chaos consistency

Only after CP1 passes.

```bash
uv run python tests/validate_cp2.py
```

Resets everything again, then drives your pipeline through: an injected
mid-stream crash (nonzero exit expected and tolerated), TWO concurrent
`pipeline.py` instances in the same group launched at once (forcing a
rebalance the moment the second one joins — both must reach idle-exit and
exit 0), a final single clean run to guarantee completion regardless of
how that rebalance happened to split partitions, and one `monitor.py` run
(a lag snapshot with `lag >= 0` must exist). Then the SAME exact-match
checks as CP1, against the SAME ground truth. A category `cnt` that comes
out too high is called out explicitly as a broken exactly-once path.

### CP3 — design writeup

Copy `src/DESIGN_TEMPLATE.md` to `DESIGN.md` in this task's directory and
fill in all six sections with reasoning grounded in what you actually
built and broke.

```bash
uv run python tests/validate_cp3.py
```

## Completion criteria

- `uv run python tests/validate_cp1.py` — PASSED.
- `uv run python tests/validate_cp2.py` — PASSED (this is the important
  one: exactly-once across an injected crash AND a two-instance
  rebalance).
- `uv run python tests/validate_cp3.py` — PASSED: DESIGN.md complete,
  CP1+CP2 still green.

## Estimated evenings

3-4 (CP1 is composing four already-solved mechanics correctly in one
transaction; CP2 is where the design actually gets proven — expect to
iterate on it more than once).

## Topics to read up on

- Composing multiple idempotent side effects behind a single dedup check,
  instead of one dedup table per effect
- Kafka's default key-based partitioner and why per-key ordering makes
  per-key state (latest-price here) race-free across a consumer group
  without any extra coordination
- Postgres row-level locking on `INSERT ... ON CONFLICT DO UPDATE` under
  concurrent writers, and why that's enough to avoid a race on shared
  aggregate rows
- What actually happens, protocol-level, when a second group member joins
  mid-stream (`session.timeout.ms`, `heartbeat.interval.ms`, partition
  revoke/assign) and what a consumer must NOT assume about in-flight work
  during that window
- Why "the offset and the write commit atomically" only has to be true
  from Postgres's side here — the RMQ contrast this whole module keeps
  coming back to: a queue has no shared, replayable bookmark a second
  consumer can pick up from; a log does
