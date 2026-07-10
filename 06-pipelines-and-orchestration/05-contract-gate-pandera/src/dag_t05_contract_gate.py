"""Skeleton for the t05_contract_gate DAG.

Copy this file into the module's dags/ directory (as dags/t05_contract_gate.py)
and fill in the TODOs there. Do not edit it in place under src/ — dags/ is
what the scheduler and dag-processor actually pick up.

This DAG reads a day's rows out of staging.price_records_raw, validates them
against the pandera contract in contracts.py, writes passing rows to
core.price_records, and routes failing rows to ops.quarantine(stage='contract').
It must be idempotent per day: rerunning it for a day whose gate already ran
must not change core or quarantine row counts.

Import contracts.py by adding this task's src/ (or wherever you've placed the
copy) onto sys.path from inside the task function — see how other tasks in
this module import local helper modules from inside `@task`-decorated
functions, since DAG files are parsed by the dag-processor in an environment
that does not automatically see this task directory.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

WAREHOUSE_CONN = "postgresql://sandbox:sandbox@warehouse:5432/pipelines"


@task
def load_and_validate(dt: str):
    """Read staging rows for `dt`, run the pandera contract, split pass/fail.

    TODO:
      - SELECT payload FROM staging.price_records_raw WHERE dt = %s, in
        line_no order (line_no matters for a stable, reproducible failure
        report — don't rely on arrival order).
      - Normalize the jsonb payloads into a typed pandas DataFrame matching
        the contract's expected dtypes (jsonb loads as plain Python objects
        via psycopg; you decide the pandas construction path).
      - Call contracts.validate_day(df, dt) (or your own equivalent) with
        lazy=True and split rows into "passing" and "failing", where each
        failing row carries a reason string suitable for
        ops.quarantine.reason.
      - Return (or otherwise pass downstream) whatever the next tasks need:
        the passing rows to load into core, the failing rows with reasons to
        load into quarantine.
    """
    raise NotImplementedError


@task
def load_core(dt: str, passing_rows):
    """Write validated rows into core.price_records for `dt`.

    TODO: make this idempotent for a rerun of the same `dt` — decide between
    delete-then-insert scoped to `dt` and an upsert on the natural key
    (source_site, product_url, scraped_at), and be deliberate about which
    one you pick and why.
    """
    raise NotImplementedError


@task
def load_quarantine(dt: str, failing_rows):
    """Write failing rows into ops.quarantine with stage='contract'.

    TODO: also needs to be safe to rerun for the same `dt` without
    duplicating quarantine rows.
    """
    raise NotImplementedError


@dag(
    dag_id="t05_contract_gate",
    schedule=None,
    start_date=datetime(2025, 6, 1),
    catchup=False,
    tags=["contract", "core"],
)
def t05_contract_gate():
    # TODO: wire load_and_validate -> load_core / load_quarantine.
    # `dt` should come from the DAG run's logical date, not be hardcoded —
    # this is how `airflow dags test t05_contract_gate 2025-06-03` picks the
    # day to run against.
    raise NotImplementedError


t05_contract_gate()
