"""Scaffold for t02_incremental_load — module 06, task 02.

Same convention as task 01: this file lives in this task's src/, copy (or
symlink) it into the shared ../dags/ folder before you run anything.

    cp src/t02_incremental_load.py ../dags/t02_incremental_load.py

Fill in the TODOs below. Nothing here runs as-is.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

RAW_DIR = "/opt/sandbox/data/raw"
WAREHOUSE_DSN = "postgresql://sandbox:sandbox@warehouse:5432/pipelines"

DAG_ID = "t02_incremental_load"


@task
def load_partition() -> dict:
    """Load one day's raw NDJSON into staging.price_records_raw, idempotently.

    "Idempotently" here means: running this task twice for the same logical
    date leaves the warehouse in the same state as running it once. No
    duplicate rows, no primary-key violations, no drift in row count.

    TODO:
    - Get the target day from context, same mechanism as task 01.
    - Read and parse that day's file the same way as task 01 (skip
      unparseable lines, count them).
    - Make the write idempotent. Two designs both satisfy the contract; pick
      one (see the README for the tradeoff):
        (a) transactional delete-then-insert: DELETE FROM
            staging.price_records_raw WHERE dt = <day>, then insert the
            freshly parsed batch, both inside the same transaction (commit
            once, at the end — a failure partway through must not leave the
            partition half-deleted or half-loaded).
        (b) upsert: INSERT ... ON CONFLICT (dt, line_no) DO UPDATE/NOTHING,
            still inside one transaction.
      Either way: the whole day's write is one atomic unit.
    - Write exactly one row to ops.load_audit for this run, regardless of
      outcome: dag_id, run_id (from context), dt, rows_loaded, status
      ("success" or "failed"). Think about what has to happen for a
      "failed" audit row to ever get written — a bare exception inside this
      function will just make the task fail; if you want a failure
      recorded, you need to catch it, write the audit row, and then decide
      whether to re-raise.
    - Return a small summary dict.
    """
    raise NotImplementedError


@dag(
    dag_id=DAG_ID,
    schedule="@daily",
    start_date=datetime(2025, 6, 1),
    end_date=datetime(2025, 6, 15),  # TODO: confirm this is the right boundary for 14 daily runs ending 06-14
    catchup=False,  # deliberate — see README for why catchup=True would undercut task 03
    tags=["module-06", "t02"],
)
def t02_incremental_load():
    load_partition()


t02_incremental_load()
