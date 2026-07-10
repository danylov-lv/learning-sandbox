# 03 — Backfill and Recovery

## Backstory

Two things are true about every real pipeline eventually: you'll need to
load history that predates when the pipeline existed, and you'll need to
repair a hole that shouldn't be there — a day someone truncated by accident,
a partition that failed silently for a week before anyone noticed. Both are
"backfill" in the loose sense, but they're operationally different: the
first is "run all 14 days," the second is "run exactly these 3 days, and
only these 3, without touching the 11 that are already correct." This task
gives you both, using the `t02_incremental_load` DAG you already built —
nothing new to implement, this is about the orchestrator's replay machinery,
not new pipeline logic.

## What's given

- Your working `t02_incremental_load` DAG from task 02, already idempotent —
  that property is what makes everything in this task safe to run more than
  once.
- `src/repair.sql` — the exact `DELETE` statement for the hole-repair drill.
  Which 3 days to delete is given; deletion is not the exercise.
- The module stack, same as tasks 01–02.

## What's required

1. Confirm `t02_incremental_load` is unpaused and its DAG file is the one
   from task 02 (still living in `../dags/t02_incremental_load.py`).
2. Backfill all 14 days (`2025-06-01` through `2025-06-14`) using Airflow 3's
   backfill CLI — **not** 14 manual `airflow dags test` calls, and not by
   flipping `catchup` and unpausing the DAG. Airflow 3 replaced the old
   `dags backfill` subcommand; find the current one yourself:

   ```
   docker compose exec airflow-scheduler airflow backfill --help
   ```

   Read the subcommand help before guessing at flags — the arguments for
   "which DAG, which date range" are what you'd expect, but get the exact
   flag names from `--help` in the actual pinned image, not from memory of
   an older Airflow version.
3. Confirm all 14 days landed correctly: staging row counts per day should
   match `ground-truth.json`'s `parseable_records`, and `ops.load_audit`
   should have at least one `success` row per day.
4. Run the hole-repair drill:
   - Apply `src/repair.sql` against the warehouse — this deletes
     `2025-06-06`, `2025-06-07`, and `2025-06-08` from
     `staging.price_records_raw`. Confirm those three days are now empty and
     the other 11 are untouched.
   - Repair only those 3 days with a **scoped** backfill (same CLI, date
     range narrowed to just the hole) — not a full 14-day rerun. The other
     11 days should not get a second load.
5. Confirm the repair worked: all 14 days back to correct counts, and
   `ops.load_audit` now shows two `success` runs for the 3 repaired days
   (the original backfill, and the repair) versus one for the other 11.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It checks,
across all 14 days:

- `staging.price_records_raw` row count per day equals `ground-truth.json`'s
  `parseable_records` for that day (no day short, no day doubled).
- No `line_no` duplication within any day (count vs. distinct count).
- `ops.load_audit` has at least 2 `success` rows for each of
  `2025-06-06`/`06-07`/`06-08`, and at least 1 `success` row for every other
  day among the 14.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if Docker is
down or any day is missing/incomplete.

## Estimated evenings

1

## Topics to read up on

- Airflow 3 backfill CLI (replacement for the deprecated `dags backfill` subcommand)
- Backfill vs catchup: same underlying idea, different trigger and different blast radius
- Scoped/partial reprocessing: repairing a specific date range without touching unaffected data
- Why idempotent task logic (task 02) is a precondition for safe backfill and repair, not an unrelated nice-to-have
