# 08 -- Capstone: Converge

## Backstory

Tasks 01-07 each proved one piece in isolation: a connector's snapshot
handing off to streaming (01), the envelope and its base64-encoded
decimals (02), upserts and deletes landing correctly downstream (03), a
column added to the source without breaking a running connector (04),
replication lag measured and alerted on (05), an idempotent exactly-once
upsert into a mart (06). None of those tasks had to survive more than one
kind of trouble at a time.

This capstone is the platform those pieces were rehearsals for: one
materializer that keeps a mart replica of `shop.offers` provably equal to
the source, while a schema change lands mid-stream, while the process gets
killed mid-transaction more than once, and while someone is watching lag
the whole time. "Provably equal" is not a figure of speech here -- CP1 and
CP2 both end with a live `SELECT` comparing every row, and a second,
independent count of every change event actually seen on the topic against
what your pipeline claims to have applied.

## What's given

- `src/pipeline.py` -- the materializer scaffold: DDL for every table it
  maintains (`replica.offers` with a from-day-one nullable
  `discount_pct` column, `mart.cap_meta`, `ops.cap_seen`), the
  `_maybe_crash` test hook (identical in spirit to earlier modules' crash
  hooks -- fires after the mart transaction commits, before the Kafka
  offset commit), and the poll loop. Stops with `raise NotImplementedError`
  in `apply_event_exactly_once`, the one place that matters: applying a
  single change event to the mart exactly once.
- `src/monitor.py` -- a lag snapshot scaffold combining consumer lag
  (Kafka side) and replication-slot lag in bytes (Postgres source side)
  into one `ops.cap_lag_snapshots` row per partition, with a simple alert
  flag. `raise NotImplementedError` at the lag computation.
- `src/DESIGN_TEMPLATE.md` -- copy to this task's root as `DESIGN.md` for
  CP3.
- `tests/validate_cp1.py`, `tests/validate_cp2.py`, `tests/validate_cp3.py`
  -- the validators. `validate_cp1.py` exposes `check_converged()` and
  `count_non_tombstone_events()`, reused by CP2 and CP3.
- `hints/`, `NOTES.md`.
- The stack from the module README (source, mart, redpanda, Connect) and
  `generate.py`'s `build_workload`. Validators register this task's own
  connector: `s08-cap` / slot `s08_cap_slot` / publication `s08_cap_pub` /
  `topic.prefix s08.cap` -> topic `s08.cap.shop.offers`.

## What's required

**CP1 (steady):** fill in `apply_event_exactly_once` so `pipeline.py`,
run once against the initial snapshot and again after a deterministic
insert/update/delete burst, leaves `replica.offers` an exact match of
`shop.offers` and `mart.cap_meta.applied_changes` exactly equal to the
number of non-tombstone events on the topic -- no double-counting, no
lost updates, across a resumed run.

**CP2 (chaos):** the same pipeline survives two injected crashes
(`S08_CRASH_AFTER`, one mid-snapshot, one mid-burst), a mid-stream
`ALTER TABLE shop.offers ADD COLUMN discount_pct` with the connector still
running, and a burst that exercises the new column, converging exactly on
the same invariants CP1 checks -- now including `discount_pct` -- plus a
`monitor.py` lag snapshot recorded somewhere in the middle of it.

**CP3 (writeup):** copy `src/DESIGN_TEMPLATE.md` to `DESIGN.md` and fill in
all five sections, grounded in what you actually built and broke; CP1 and
CP2 must both still pass.

Try it by hand before trusting the validators:

```bash
uv run python src/pipeline.py                        # normal run, no crash
S08_CRASH_AFTER=9000 uv run python src/pipeline.py    # dies partway
uv run python src/pipeline.py                         # resumes and catches up
uv run python src/monitor.py                          # one lag snapshot
```

## Completion criteria

- `uv run python tests/validate_cp1.py` -- PASSED.
- `uv run python tests/validate_cp2.py` -- PASSED.
- `uv run python tests/validate_cp3.py` -- PASSED: `DESIGN.md` complete,
  CP1 and CP2 still green.

Every validator prints `PASSED` or `NOT PASSED: <reason>` and exits 0/1;
timeouts are generous -- grading is on exact convergence against ground
truth and live source state, not wall-clock.

## Estimated evenings

3-5 (CP1 composes exactly-once dedup, upsert-or-delete, and an exact
aggregate correctly; CP2 is where it actually gets proven under two
crashes and a live schema change -- expect to iterate).

## Topics to read up on

- End-to-end CDC materialization: source -> Debezium -> Kafka -> mart, as
  one pipeline instead of four separate exercises
- Exactly-once apply under a process crash: dedup key choice
  (offset-pair vs. LSN) and why the Kafka offset commit sits outside the
  atomic unit
- Additive schema evolution on a live connector: what changes on the wire,
  what a consumer must read defensively
- Replica lag and alerting: consumer lag vs. replication-slot lag, and why
  they can diverge
- Convergence testing: proving `mart == source` with an independent check
  instead of trusting the pipeline's own bookkeeping
- What changes about this design at 10x event volume
