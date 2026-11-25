# 02 — Incremental, Idempotent Loads

## Backstory

Task 01 got one day's data into staging, once, by hand-triggering a run.
That's not a pipeline, that's a script with extra ceremony. A real nightly
feed has to run on a schedule, cover a fixed historical range, and — this is
the part that actually matters in production — survive being run twice for
the same day without anyone noticing. Schedulers retry tasks. People
re-trigger runs after fixing a bug. Someone fat-fingers a backfill. If your
load logic isn't idempotent, every one of those ordinary events either
double-counts data or requires a manual cleanup query at 2am. This task
makes idempotency the graded property, not a nice-to-have: the validator
doesn't just check your data once, it *reruns your DAG itself* and checks
that nothing changed.

## What's given

- `src/t02_incremental_load.py` — DAG skeleton, one task (`load_partition`),
  scheduled `@daily` across exactly `2025-06-01`..`2025-06-14`, `catchup`
  fixed to `False`.
- Your `t01_raw_to_staging` DAG and the tables it already created — this
  task writes into the same `staging.price_records_raw`, plus
  `ops.load_audit` for the first time.
- The module stack, same as task 01.

## What's required

1. Copy the skeleton into `../dags/t02_incremental_load.py`.
2. Implement `load_partition`. Read its docstring for the exact contract.
   You get to choose between two idempotent designs:
   - **Delete-then-insert**: wipe the day's existing rows, insert the fresh
     batch, one transaction. Simple to reason about; every run fully
     rewrites the partition regardless of what changed.
   - **Upsert**: `INSERT ... ON CONFLICT (dt, line_no) DO UPDATE` (or `DO
     NOTHING`, if you've convinced yourself the payload for a given
     `(dt, line_no)` never legitimately changes between runs against the
     same static file — is that true here?). Touches only what's different,
     but you have to get the conflict target and action right.

   Both are graded the same way: the validator only cares about the
   *outcome* of running twice, not which strategy you picked. Write down in
   `NOTES.md` which one you chose and why.
3. Write exactly one `ops.load_audit` row per DAG run, `status` = `success`
   or `failed`.
4. About `catchup=False`: this DAG's schedule spans 14 fixed past days, which
   is exactly the situation `catchup=True` exists for — a scheduler would
   normally back-run every missed interval the moment you unpause the DAG.
   It's deliberately off here because task 03 turns backfilling into an
   explicit, controlled action (the CLI backfill command, plus a scoped
   repair of specific days) rather than something that happens automatically
   and invisibly the moment a DAG is unpaused. Keep it `False` — you'll load
   history on purpose, not by accident.
5. Load `2025-06-03` at least once:

   ```
   docker compose exec airflow-scheduler airflow dags test t02_incremental_load 2025-06-03
   ```

6. Prove idempotency to yourself before running the validator: run the same
   command again for the same date, then check `staging.price_records_raw`
   row count and `ops.load_audit` row count haven't done anything
   surprising.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Requires `2025-06-03` already loaded (fails with a clear message if not).
- Records the current staging row count and `ops.load_audit` row count for
  `2025-06-03`.
- Triggers **one more run itself**: `docker compose exec -T
  airflow-scheduler airflow dags test t02_incremental_load 2025-06-03` (from
  the module directory). This is the actual idempotency proof — the
  validator does not trust your own claim that reruns are safe.
- Asserts: staging row count for `2025-06-03` is unchanged and equals
  `ground-truth.json`'s `parseable_records` for that day; no `line_no`
  duplication occurred; `ops.load_audit` gained exactly one new row, with
  `status = 'success'`.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if Docker is
down, the self-triggered rerun fails to execute, or the day was never loaded.

## Estimated evenings

1

## Topics to read up on

- Idempotent writes: delete-then-insert vs upsert, and what "same input, same output" means for a batch load
- Postgres `INSERT ... ON CONFLICT` (upsert) semantics
- Transaction boundaries: why the delete and the insert (or the whole upsert batch) need to commit as one unit
- Airflow scheduling: `@daily`, `start_date`/`end_date`, and what `catchup` actually controls
- Audit/ledger tables as an observability pattern independent of the data they describe

## Rerun cost, if you're curious

`docker compose exec` shells out per invocation; the validator's self-triggered
rerun adds a few seconds of wall time on top of whatever `load_partition`
itself takes. Nothing to optimize here, just don't be surprised the
validator takes longer than task 01's did.
