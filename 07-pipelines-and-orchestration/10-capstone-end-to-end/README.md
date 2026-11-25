# 10 — Capstone: End to End

## Backstory

The price-intelligence platform goes to production. Everything you built
in tasks 01-07 — the quarantining ingest, the pandera contract gate, the
incremental core loader, the Spark silver-lake stage, the alerting — has
so far lived as separate DAGs, each proving one concept. Production does
not run concepts. It runs one pipeline, end to end, that a person on call
can reason about at 3am: where did this day's data stop, what got
quarantined and why, which partitions are safe to rebuild, and what will
a re-run touch.

This capstone is that pipeline. You compose your previous work into a
single DAG, evolve the contract one more time (the upstream scrapers are
not done changing things), add the mart layer the analysts have been
waiting for, backfill all fourteen days through it — and then prove it
survives real failures, because a pipeline that has never been broken on
purpose has never been tested. Three checkpoints: build it, break it and
recover, then write the design down.

## What's given

- Everything from tasks 01-07: `staging.price_records_raw`,
  `ops.load_audit`, `ops.quarantine`, `core.price_records`, your contract
  code, your Spark s3a stage, the alert-sink contract. This task assumes
  they exist and work; it adds one new table and one new raw day.
- `src/ddl.sql` — the DDL for `mart.daily_category_prices`, the one new
  table. Run it once against the warehouse before the mart stage first
  executes.
- `src/t10_capstone_dag.py` — DAG skeleton (dag_id `t10_capstone`), all
  task bodies stubbed. Copy it into the module's `dags/` directory and
  iterate there; `src/` is not scanned by the scheduler.
- `src/contract_v3.py` — scaffold spelling out exactly what the evolved
  contract must handle (optional `seller_rating`, locale-price
  normalization) with stub functions.
- `src/DESIGN_TEMPLATE.md` — copy to this task's root as `DESIGN.md` for
  CP3.
- `tests/drill_break_midstate.py`, `tests/drill_new_drift.py` — CP2's
  failure-drill tooling, fully implemented and not yours to edit. They
  create broken *input states* and record what they planted into
  gitignored `*-local.json` manifests; they contain no pipeline logic.
- `tests/validate_cp1.py`, `tests/validate_cp2.py`,
  `tests/validate_cp3.py` — the validators.
- `NOTES.md` — measurement tables to fill in as you go.

## What's required

One DAG, `t10_capstone`, processing one day-partition per run:

1. **Ingest + quarantine** — raw NDJSON for the run's `dt` into
   `staging.price_records_raw`; malformed lines to `ops.quarantine`
   (stage `ingest`).
2. **Contract gate (v3)** — the evolved contract: `seller_rating` is
   optional (absent before 2025-06-10, a float in [1.0, 5.0] after);
   `price` is normalized from either a JSON number or a locale-formatted
   string (US `"$1,299.00"` / EU `"1.299,00 EUR"`) into a numeric value
   *before* validation. Failing records to `ops.quarantine` (stage
   `contract`); a dominant-reason failure spike fires a
   `type='contract_drift'` alert.
3. **Core load** — contract-passing records upserted into
   `core.price_records`, deduplicated on the natural key; an
   `ops.load_audit` row per run.
4. **Silver lake** — the day's core records written as parquet to
   `s3a://lake-06/silver/prices/dt=<day>/` via the embedded Spark.
5. **Mart build** — `mart.daily_category_prices` upserted for the day
   from core (see `src/ddl.sql` for grain and columns).
6. **Ops summary + alerting** — quarantine-rate check
   (`type='quarantine_rate'`), failure alerting (`type='dag_failure'`),
   posted to the alert-sink.

Every stage idempotent per day-partition: re-running any day, any number
of times, changes nothing that was already correct — no duplicate core
rows, no doubled quarantine entries, no appended lake files, no stale
mart rows.

### Checkpoint 1 — build + full backfill

Implement the DAG and push all 14 days (2025-06-01..14) through it:

```bash
docker compose exec airflow-scheduler airflow dags test t10_capstone 2025-06-01
# ... or a bounded backfill, your choice — but know what each touches
uv run python tests/validate_cp1.py
```

### Checkpoint 2 — failure drills

Only after CP1 passes. Drill one: a half-dead pipeline.

```bash
uv run python tests/drill_break_midstate.py   # kills mart + lake for 3 days
# recover ONLY those 3 days, then:
uv run python tests/validate_cp2.py --midstate
```

The validator re-checks all CP1 conditions, then proves your recovery was
*scoped*: unaffected days' `core.loaded_at` must be byte-identical to the
pre-drill snapshot, and no unaffected day may show a new audit row. "Just
re-backfill everything" fails this on purpose.

Drill two: new, uncovered schema drift.

```bash
uv run python tests/drill_new_drift.py        # plants dt=2025-06-15
# run your pipeline for 2025-06-15, then:
uv run python tests/validate_cp2.py --drift
```

~40% of the planted day's records renamed `currency` to `currency_code`.
Your contract must catch it per-record (quarantine, not crash), the
unaffected ~60% must load normally, a `contract_drift` alert must fire,
and days 01-14 downstream must be untouched. The drill prints the counts
it planted; the validator holds you to them.

### Checkpoint 3 — design writeup

Copy `src/DESIGN_TEMPLATE.md` to `DESIGN.md` in this task's directory and
fill in all six sections with reasoning grounded in what you actually
built and broke.

```bash
uv run python tests/validate_cp3.py
```

## Completion criteria

- `uv run python tests/validate_cp1.py` — PASSED: all 14 days' core
  counts match ground truth exactly; per-currency sums within 0.02; mart
  internally consistent with core (independently recomputed); a silver
  partition per day whose row count equals that day's core count; audit
  rows present.
- `uv run python tests/validate_cp2.py` — PASSED for both drills.
- `uv run python tests/validate_cp3.py` — PASSED: DESIGN.md complete and
  substantial, CP1+CP2 still green.

## Estimated evenings

2-4 (CP1 is the bulk; CP2 is fast if CP1's idempotency is real, and slow
if it isn't — which is the lesson).

## Topics to read up on

- Airflow logical dates, data intervals, and `dags test` vs. `backfill`
  vs. clearing task instances — what each actually re-executes
- Idempotent load patterns: upsert vs. delete-and-reload per partition,
  and what each does to audit columns like `loaded_at`
- Task-level vs. DAG-level retries, trigger rules for cleanup/alerting
  tasks that must run on upstream failure
- Data contracts in practice: additive vs. breaking schema changes,
  quarantine-vs-crash as a contract-violation policy
- Locale-dependent number formatting and why parsing prices with a regex
  you wrote at midnight is a production incident waiting to happen
- Overwriting a single parquet partition on an object store without
  touching sibling partitions
- Alert fatigue: paging thresholds vs. log-only signals in data pipelines
