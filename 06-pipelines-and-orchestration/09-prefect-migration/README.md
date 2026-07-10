# 09 — Prefect Migration

## Backstory

The on-call rotation has been grumbling about Airflow: standing up the
metadata db, scheduler, webserver, and DAG-file-processor just to run one
incremental loader feels like a lot of ceremony for a small team. Someone
on the platform team has been pushing Prefect as a lighter alternative and
wants a real comparison, not a blog-post opinion. You're asked to port the
incremental price-record loader — the one you built in task 02 against
Airflow — to a Prefect 3 flow, run it for real, and write down what
actually differs once you've done both, not what the marketing decks claim.

## What's given

- `src/flow.py` — a stub with `@task`/`@flow`-decorated function signatures
  left as `NotImplementedError`, an `argparse` CLI already wired to
  `--date`, and a `main()` that calls the flow. You fill in the four
  functions and the flow body.
- `COMPARISON.md` at the task root — a template with the five required
  section headings already in place as questions to answer, no answers
  filled in.
- The same module 06 warehouse your task 02 DAG already writes to
  (`localhost:54306`, db `pipelines`, user/pass `sandbox`, schemas
  `staging`/`core`/`mart`/`ops`) and the same raw data layout
  (`data/raw/dt=YYYY-MM-DD/prices.ndjson`).
- `staging.price_records_raw(dt, line_no, payload jsonb, loaded_at, PRIMARY
  KEY (dt, line_no))` and `ops.load_audit(id, dag_id, run_id, dt,
  rows_loaded, status, finished_at)` already exist from earlier tasks — this
  flow loads into the same tables, it does not create its own.

## What's required

1. Implement the four task functions in `src/flow.py`:
   - Read the day's raw ndjson file line by line.
   - Parse each line as JSON; a line that fails to parse is a malformed
     (poison) line and is skipped, not stored.
   - Load every successfully-parsed line into `staging.price_records_raw`
     keyed on `(dt, line_no)` — one row per parseable line, upserted
     idempotently (running the same date twice must not change the row
     count or duplicate rows).
   - Write one row to `ops.load_audit` per run, with `dag_id =
     'prefect:incremental_load'`.
2. Configure retries on the tasks that talk to the outside world (file
   read, warehouse writes) — pick numbers you can justify, not just
   defaults left untouched.
3. The flow must be runnable directly from the host, no Prefect server
   required:
   ```
   uv run python src/flow.py --date 2025-06-03
   ```
   Prefect 3 uses an ephemeral local API for this by default. If you want
   the UI while iterating, `prefect server start` in another terminal
   (default port `http://localhost:4200`) works alongside it — entirely
   optional, not needed for grading.
4. Fill in every section of `COMPARISON.md` with substance from your own
   experience porting and running both versions — see the questions already
   written into each section.

## Completion criteria

From this task's directory:

```
uv run python tests/validate.py
```

The validator runs `src/flow.py --date 2025-06-04` twice (a date not used
by any other task's validator), and checks: both runs exit 0; after the
first run, `staging.price_records_raw` has exactly as many rows for that
date as `data/ground-truth.json`'s `parseable_records` count for it; the
row count is unchanged after the second run (idempotency); `ops.load_audit`
has at least two rows for `dag_id='prefect:incremental_load'` on that date;
and `COMPARISON.md` has all five required section headings filled with a
substantial amount of content beyond the given template.

## Estimated evenings

1

## Topics to read up on

- Prefect 3 `@flow`/`@task` decorators and the ephemeral local API
- Prefect retries (`retries`, `retry_delay_seconds`) vs. Airflow's
  retry/backoff model
- Idempotent upsert patterns (`ON CONFLICT ... DO UPDATE`) for exactly-once
  style loading semantics
- Prefect deployments/work pools vs. Airflow's scheduler+executor model (for
  the comparison, conceptually — you don't need to deploy anything)
