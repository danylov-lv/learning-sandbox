"""Scaffold for t01_raw_to_staging — module 06, task 01.

This file lives here, in the task's src/, not in the module's dags/. That is
the convention for every DAG in this module: dags/ is a single shared folder
mounted into every Airflow container, so a task's scaffold is written in
src/ and you copy (or symlink) it into ../dags/ yourself once you start
working on it. Every later task follows the same pattern.

    cp src/t01_raw_to_staging.py ../dags/t01_raw_to_staging.py

Fill in the TODOs below. Nothing here runs as-is.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

RAW_DIR = "/opt/sandbox/data/raw"  # bind-mounted from ./data, see docker-compose.yml
WAREHOUSE_DSN = "postgresql://sandbox:sandbox@warehouse:5432/pipelines"


@task
def load_day() -> dict:
    """Load one day's raw NDJSON dump into staging.price_records_raw.

    TODO:
    - Figure out the target day. This DAG is manually triggered per logical
      date (no fixed schedule) — the day to load is the run's logical date,
      not "today". Look at how Airflow 3 TaskFlow tasks read context (Jinja
      templated context variables like `ds`, or `get_current_context()` from
      `airflow.sdk`). Don't hardcode a date.
    - Build the path to that day's file: f"{RAW_DIR}/dt=<day>/prices.ndjson".
    - Read the file line by line. Each line is meant to be one JSON object.
      Some lines are malformed on purpose (truncated JSON, dangling braces,
      non-JSON garbage) — json.loads will raise on those. Skip them, but
      count how many you skipped and log that count somewhere visible
      (a log line is enough for this task).
    - For every line that DOES parse, insert one row into
      staging.price_records_raw(dt, line_no, payload). `line_no` must be the
      1-based line number of that line in the *source file* — i.e. stable
      and reproducible if you rerun this today, not a renumbering of only the
      parseable lines.
    - Insert in batches (psycopg's executemany, or COPY — your choice, this
      task doesn't grade which one).
    - Return a small summary, e.g. {"rows_loaded": ..., "skipped": ...}.
    """
    raise NotImplementedError


@dag(
    dag_id="t01_raw_to_staging",
    schedule=None,
    start_date=datetime(2025, 6, 1),
    catchup=False,
    tags=["module-06", "t01"],
)
def t01_raw_to_staging():
    load_day()


t01_raw_to_staging()
