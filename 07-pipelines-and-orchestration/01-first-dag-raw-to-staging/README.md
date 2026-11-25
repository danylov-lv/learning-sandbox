# 01 — First DAG: Raw to Staging

## Backstory

PriceWatch's nightly scraper has been dumping raw NDJSON to disk for two
weeks and nobody has built the pipe that turns those dumps into anything a
BI person or a pricing model can query. You've run queues, workers, and k8s
jobs for years, so "read a file, write it to a database, don't crash on bad
input" is not new. What's new is doing that inside an orchestrator that owns
scheduling, retries, and historical replay for you — instead of a cron job
and a prayer. This task is deliberately the smallest possible slice: one DAG,
one task, one day, no incremental logic, no idempotency guarantees yet. Get
comfortable with the shape of a DAG and how Airflow hands you "which day am I
running for" before task 02 makes that day a moving, replayable target.

## What's given

- `src/ddl.sql` — the exact `staging.price_records_raw` and `ops.load_audit`
  table definitions. Apply them as given; every later task in this module
  assumes this shape.
- `src/t01_raw_to_staging.py` — a DAG skeleton with one task function,
  `load_day`, that raises `NotImplementedError`. Full contract in its
  docstring.
- The module's `docker-compose.yml` stack: warehouse Postgres on host port
  `54306` (db `pipelines`, user/password `sandbox`/`sandbox`), Airflow UI on
  `8306` (admin/admin), raw dumps bind-mounted into every Airflow container
  at `/opt/sandbox/data/raw/dt=YYYY-MM-DD/prices.ndjson`.
- The module-wide convention: `dags/` at the module root is a single shared
  folder mounted into all Airflow containers. DAG scaffolds live in each
  task's `src/`; you copy (or symlink) the file into `../dags/` yourself once
  you start. Every later task in this module follows the same pattern —
  state managed this way (which DAG file is "live" in `dags/`) is on you.

## What's required

1. Bring the stack up (see module README) and apply `src/ddl.sql` against
   the warehouse.
2. Copy `src/t01_raw_to_staging.py` into `../dags/t01_raw_to_staging.py`.
3. Implement `load_day` per its docstring: for the DAG run's logical date,
   read that day's `prices.ndjson`, skip lines that fail to parse as JSON
   (log how many), and insert the rest into `staging.price_records_raw` with
   a `line_no` equal to the line's position in the source file.
4. Run it for `2025-06-01`:

   ```
   docker compose exec airflow-scheduler airflow dags test t01_raw_to_staging 2025-06-01
   ```

   Iterate on this loop — it runs the DAG in-process against the real
   warehouse, no scheduler wait.
5. Confirm the DAG is also discoverable and parses cleanly:
   `airflow dags list-import-errors` (inside any Airflow container) should
   not mention it.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It prints
`PASSED` when, for `dt = 2025-06-01`:

- `staging.price_records_raw` exists and has exactly
  `ground-truth.json`'s `per_day["2025-06-01"].parseable_records` rows for
  that day.
- Every one of those rows has a non-null `payload`.
- `line_no` values for that day are all distinct (no row silently
  overwrote another — the primary key would have rejected a collision, but
  the check is explicit here as a sanity signal).
- The gap between the raw file's total line count and what landed in
  staging equals `ground-truth.json`'s `malformed_lines` for that day — i.e.
  exactly the malformed lines got skipped, nothing else.

The validator fails gracefully (`NOT PASSED: <reason>`, exit 1, no
traceback) if Docker isn't up, the tables don't exist yet, or the DAG hasn't
been run.

## Estimated evenings

1

## Topics to read up on

- Airflow 3 TaskFlow API (`airflow.sdk`) vs the older `airflow.decorators`/operator style
- Logical date vs "wall clock now" and why a manually-triggered DAG still has one
- Jinja templated context variables in Airflow tasks (`ds`, `get_current_context()`)
- `airflow dags test` as a fast local iteration loop
- Batched inserts with psycopg (`executemany` vs `COPY`)
- JSON Lines as a scrape-dump format and why line-oriented parsing tolerates partial corruption better than parsing the whole file as one JSON document
