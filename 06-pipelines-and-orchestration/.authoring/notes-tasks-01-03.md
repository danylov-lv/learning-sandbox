# Authoring notes: tasks 01-03 (raw-to-staging, idempotent loads, backfill)

Off-limits for learners before attempting the tasks. Documents intended
solution shapes, validator logic, and what the live verification pass must
confirm. Written from a static-only session (module stack was down; nothing
was executed against Airflow or the warehouse).

## Shared conventions established here

- DAG files: scaffolds live in each task's `src/`; the learner copies or
  symlinks them into module-root `dags/` (single shared mounted folder).
  Stated in task 01's README as the module-wide convention; tasks 02+ assume
  it.
- DDL is given, not derived: `01-first-dag-raw-to-staging/src/ddl.sql` holds
  the exact `staging.price_records_raw` and `ops.load_audit` definitions from
  `design.md`'s shared contract. `CREATE TABLE IF NOT EXISTS`, so re-applying
  is harmless.
- All three validators run host-side via `uv run python tests/validate.py`
  from the task dir, with a `sys.path.insert(0, MODULE_ROOT)` shim to import
  `harness/common.py`. They set `PGCONNECT_TIMEOUT=5` (env, setdefault) so a
  down stack fails in ~10s instead of hanging; `pg_connect()` then produces
  the graceful `NOT PASSED: could not connect...` message.
- Repaired-days constant for task 03: `2025-06-06`, `2025-06-07`,
  `2025-06-08` (middle of the range, hardcoded in both `src/repair.sql` and
  `tests/validate.py` — keep in sync if ever changed).

## Task 01 — first DAG, raw to staging

Intended solution shape: single `@task` (`load_day`) in
`t01_raw_to_staging`, `schedule=None`, manually triggered via
`airflow dags test t01_raw_to_staging 2025-06-01`. The task reads the logical
date from context (either `get_current_context()` from `airflow.sdk` or a
`ds`-named parameter injected by TaskFlow), opens
`/opt/sandbox/data/raw/dt=<ds>/prices.ndjson`, enumerates lines from 1,
`json.loads` per line, skips and counts failures, collects
`(ds, line_no, Jsonb(payload))` and writes once via `executemany` (or COPY
with self-serialized JSON) to `staging.price_records_raw`, connecting to
`postgresql://sandbox:sandbox@warehouse:5432/pipelines`. No audit row in this
task (`ops.load_audit` first used in task 02).

Validator (`tests/validate.py`, day fixed to 2025-06-01):
- `count(*)`, `count(distinct line_no)`, `count(payload)` for the day in one
  query.
- `count(*) == per_day["2025-06-01"].parseable_records` (38580).
- `distinct line_no == count(*)` (belt-and-braces; PK already enforces).
- `count(payload) == count(*)` (non-null payload; column is NOT NULL anyway,
  the check exists for the failure message, not the constraint).
- Malformed-skip identity: `total_lines - rows_loaded == malformed_lines`
  (38735 - 38580 == 155). This is the GT identity
  `parseable_records = total_lines - malformed_lines` from design.md, checked
  from the other side.
- Graceful failures: no docker (connect timeout), missing table
  (UndefinedTable caught), zero rows (DAG never run).

GT keys used: `per_day[day].{parseable_records,total_lines,malformed_lines}`.

## Task 02 — incremental, idempotent loads

Intended solution shape: `t02_incremental_load`, `schedule="@daily"`,
`start_date=2025-06-01`, `end_date=2025-06-15`, `catchup=False` (README
explains: backfilling history is deliberately manual, it's task 03's
subject). One `@task` `load_partition`: same parse as task 01, then either
transactional delete-then-insert of the day partition or
`ON CONFLICT (dt, line_no) DO UPDATE` upsert — learner's choice, README
frames the tradeoff, validator is strategy-agnostic. One `ops.load_audit`
row per run inside the same transaction on success; on exception, a fresh
connection writes a `failed` row and re-raises (hint-3 sketches this).
`run_id` comes from context.

Validator (day fixed to 2025-06-03):
- Preconditions: staging rows for the day > 0 and audit rows for
  (dag_id, day) > 0, else NOT PASSED with instructions.
- Captures before-state: staging count, distinct line_no, audit total count,
  audit success count.
- Self-triggers one rerun:
  `docker compose exec -T airflow-scheduler airflow dags test
  t02_incremental_load 2025-06-03`, `cwd=MODULE_ROOT`, 300s timeout,
  captured output; nonzero exit or timeout or missing docker binary ->
  graceful NOT PASSED (with output tail).
- After-state assertions: staging count unchanged AND
  `== per_day["2025-06-03"].parseable_records` (49269); distinct line_no ==
  count (no PK-dodging duplication); audit total exactly +1; audit success
  exactly +1.

GT keys used: `per_day["2025-06-03"].parseable_records`.

Note: the exactly-+1 audit assertions mean a learner whose task writes two
audit rows per run (e.g. an "attempt started" row plus a final row) fails —
intentional, the contract says one row per run.

## Task 03 — backfill and recovery

No new DAG; reuses the learner's t02. `src/repair.sql` is given verbatim
(DELETE of the 3 middle days) because deletion is not the exercise. Flow:
full-range backfill via the Airflow 3 backfill CLI (2025-06-01..14), verify,
apply repair.sql, scoped backfill of only 06-06..06-08, verify.

Validator (state-only, does not run the CLI):
- Per day, all 14: staging count == `per_day[day].parseable_records`, count
  == distinct line_no, 0 rows -> "backfill not run yet".
- Per day audit: success rows `>= 2` for the 3 repaired days, `>= 1` for the
  other 11 (dag_id = t02_incremental_load). `>=` not `==` because the learner
  may have run t02 extra times while iterating; the invariant that proves the
  repair happened is the repaired days having at least one MORE success than
  a single backfill would give.

GT keys used: `days` (must be 14), `per_day[*].parseable_records`.

Caveat: a learner who already ran t02 twice for a repaired day during task 02
iteration (e.g. 06-03 is NOT in the repaired set, so no interference from the
task-02 validator's own rerun) could in theory satisfy `>= 2` without doing
the scoped backfill for 06-06..08 — only if they manually `dags test`-ed
those exact 3 days twice. Accepted as unlikely-and-self-defeating; the
alternative (== checks) breaks on legitimate retries.

## To confirm in the live verification pass

1. **Airflow 3.1 backfill CLI syntax — UNVERIFIED.** The stack was down all
   session; nothing names exact flags anywhere in the task text on purpose
   (README/hints direct the learner to `airflow backfill --help` inside the
   container, hint-2/3 say "something like `create`"). Verify inside the
   pinned `apache/airflow:3.1.0` image:
   `docker compose exec airflow-scheduler airflow backfill --help` and the
   subcommand's own `--help`. Expected (from 3.x docs knowledge, to be
   confirmed): `airflow backfill create --dag-id t02_incremental_load
   --from-date 2025-06-01 --to-date 2025-06-14`, plus a reprocess-behavior
   flag (something like `--reprocess-behavior completed` / `failed` / `none`)
   that the *repair* pass likely needs, since the 3 repaired dates already
   have successful runs recorded. If the real flags differ, hint-3 step 5's
   phrasing ("look for whatever flag controls reprocessing/force behavior")
   still holds, but confirm it's actually discoverable from `--help`.
2. **Does `airflow backfill create` require the DAG to be unpaused and the
   scheduler to pick the backfill up?** (In 3.x backfills run through the
   scheduler, unlike 2.x's in-process `dags backfill`.) If runs sit queued
   while the DAG is paused, the README's step "confirm the DAG is unpaused"
   is load-bearing — verify and, if needed, make that instruction more
   prominent.
3. **`airflow dags test` with a `start_date=2025-06-01` DAG and logical date
   2025-06-01**: confirm `dags test t02_incremental_load 2025-06-03` works
   for a `@daily` DAG with an `end_date` and `catchup=False` (it should — it
   bypasses the scheduler entirely) and that `run_id` is present in context
   under `dags test`.
4. **Context access in Airflow 3.1 TaskFlow**: confirm both mechanisms
   hint-2 (task 01) describes — `airflow.sdk.get_current_context()` and
   `ds`-named parameter injection — actually work in the pinned image, and
   that `ds` is the right key name for the YYYY-MM-DD string.
5. **`end_date=datetime(2025, 6, 15)` boundary** in the t02 scaffold: the
   scaffold carries a TODO telling the learner to confirm this yields exactly
   the 14 data intervals 06-01..06-14 (Airflow 3 `@daily` runs for interval
   [d, d+1) at d+1; last interval start must be 06-14). Verify the full
   backfill actually produces runs with logical dates 06-01..06-14 inclusive
   and nothing for 06-15.
6. **Pass paths**: with the stack up, build a throwaway reference
   implementation in a gitignored scratch dir (never committed), run tasks
   01->02->03 end to end, and confirm each validator PASSES, including task
   02's self-triggered rerun (+1 audit row semantics) and task 03's >= 2 /
   >= 1 audit split after the scoped repair.
7. **jsonb adaptation**: hint-2 (task 01) points at `psycopg.types.json.Jsonb`
   — confirm that's the correct import path in psycopg 3.3.x.

## Static checks already done (this session)

- `py_compile` clean on all 5 committed .py files (2 scaffolds, 3
  validators).
- All three validators run with the stack down print a single
  `NOT PASSED: could not connect to Postgres on port 54306: ...` and exit 1,
  no traceback.
- GT arithmetic spot-checked against the committed `data/ground-truth.json`:
  2025-06-01 total 38735 / malformed 155 / parseable 38580;
  2025-06-03 parseable 49269. Identity
  `parseable = total - malformed` holds for all 14 days.
