# 05 — Contract gate (pandera)

## Backstory

The upstream scraping team ships whatever they ship. So far you've been
loading their raw dumps into `staging.price_records_raw` and building
whatever downstream logic you needed on faith that the payloads look like
what the brief said they'd look like. That faith has no enforcement behind
it — nothing stops a malformed batch, a corrupted field, or a silent schema
change from flowing straight into `core` and poisoning every report built on
top of it.

Today you build the gate. Every row crossing from `staging` into `core` gets
checked against an explicit, machine-enforced contract. Rows that violate it
don't get silently dropped or silently coerced — they get quarantined with a
reason, so someone can go look.

## What's given

- `src/ddl.sql` — DDL for the three tables this task touches:
  `staging.price_records_raw` and `ops.quarantine` (carried over from earlier
  tasks in this module, repeated here so this file runs standalone) and
  `core.price_records`, introduced in this task. Run it once against the
  warehouse before you start.
- `src/contracts.py` — a skeleton `pandera.pandas.DataFrameSchema` with the
  imports and structure in place, and TODOs marking which business rules it
  needs to express. You fill in the schema.
- `src/dag_t05_contract_gate.py` — a DAG skeleton with task stubs and
  docstrings describing what each stub needs to do. Copy it into the module's
  `dags/` directory as `dags/t05_contract_gate.py` and fill it in there —
  don't edit it in place under `src/`, the scheduler and dag-processor only
  see `dags/`.
- `harness/common.py` at the module root, for validator-side helpers
  (ground truth loading, Postgres connection info, alert reading). You won't
  need it for the DAG itself, only if you want to poke at things the way the
  validator does.

**Scope note on input data**: this DAG's job is to read whatever is currently
sitting in `staging.price_records_raw` for a given day and run it through the
contract. It does not care how that staging data got there or whether an
earlier stage already filtered anything out — for this task, assume staging
holds every line from the day's raw file that parsed as JSON at all
(including the ones that are schema-invalid, and including exact duplicate
lines). The contract gate is what's supposed to catch the invalid ones; if
staging had already filtered them out, this task would have nothing to do.

## What's required

1. Fill in `PRICE_RECORD_SCHEMA` in `src/contracts.py`: a pandera schema
   expressing the record contract as described in the shared design brief
   for this module (ask around / check earlier tasks' notes on the record
   shape if you don't already have it memorized) —
   - every field required and non-null with the right dtype
   - `price` strictly positive and below a sane absurdity ceiling — and
     before you reach for a single number, think about what "absurd" means
     in a dataset where categories have wildly different price ranges
   - `currency` restricted to the allowed set
   - `product_url` non-null and matching the expected URL shape
   - `scraped_at` falling inside the partition day being validated
   - the schema should be strict about columns it doesn't know about —
     decide for yourself whether that's the right default for a boundary
     like this one, and set it accordingly.
2. Build the DAG `t05_contract_gate` (from the given skeleton) so that, for a
   given logical date `dt`:
   - it reads that day's rows out of `staging.price_records_raw`,
   - normalizes the jsonb payloads into a typed pandas frame,
   - validates the frame against the contract with `lazy=True` (you want
     every failure reported, not just the first),
   - writes every row that passes into `core.price_records`,
   - writes every row that fails into `ops.quarantine` with
     `stage='contract'` and a `reason` derived from pandera's failure
     output.
3. Make the whole thing idempotent per day: running `t05_contract_gate` twice
   for the same `dt` must leave `core.price_records` and `ops.quarantine` in
   the same state as running it once. Think about what "the same natural
   key showing up twice" means for each of the two target tables, and about
   what the `UNIQUE` constraint on `core.price_records` is already doing for
   you before you reach for extra dedup logic.
4. Run the gate for `2025-06-01` through `2025-06-05` (use
   `docker compose exec airflow-scheduler airflow dags test t05_contract_gate <date>`
   for the fast iteration loop — no need to wait on the scheduler).

## Completion criteria

`uv run python tests/validate.py` from this task's directory passes. It
checks, for `2025-06-01..2025-06-05`: `core.price_records` row counts and
per-currency price sums against an independent ground truth, that
`ops.quarantine(stage='contract')` counts are consistent with the known
count of invalid records for each day, and that rerunning the gate for one
of those days changes nothing.

## Estimated evenings

1

## Topics to read up on

- pandera `DataFrameSchema` / `Column` / `Check`, lazy validation and
  `SchemaErrors.failure_cases`
- `strict` mode in pandera schemas and what it's actually protecting against
- Airflow 3 TaskFlow API (`airflow.sdk`), `dags test` for local iteration
- idempotent load patterns: delete-then-insert vs. `ON CONFLICT` upsert
- natural keys vs. surrogate keys, and what a `UNIQUE` constraint buys you
  for free in a dedup problem
