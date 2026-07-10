"""Scaffold for the capstone DAG, dag_id="t10_capstone".

Copy this file into the module's dags/ directory before iterating on it
(dags/ is read by the scheduler and dag-processor; src/ here is not). Use
`docker compose exec airflow-scheduler airflow dags test t10_capstone <date>`
for the fast loop instead of waiting on the scheduler.

This is a skeleton, not a working DAG — every task body below is a stub.
You are composing/refactoring work you already have from tasks 01-07
(ingest+quarantine, contract gate, core load) into one DAG, then adding the
three stages this capstone introduces: an evolved v3 contract, a Spark
silver-lake write, and a mart build with alerting. Nothing here should be
copy-pasted verbatim from an earlier task without reconsidering it for
idempotent, per-day-partition re-runs — that is the whole point of the
capstone.

Required stage order (fan the logical_date/dt through every stage):

    ingest (raw ndjson -> staging.price_records_raw, malformed lines ->
            ops.quarantine stage='ingest')
      -> contract gate (v3: seller_rating optional, locale-price
         normalization; failing rows -> ops.quarantine stage='contract')
      -> core load (core.price_records, upsert/idempotent per dt)
      -> silver lake write (Spark, parquet, s3a://lake-06/silver/prices/dt=<day>/)
      -> mart build (mart.daily_category_prices, upsert per dt)
      -> ops summary + alerting (quarantine-rate, contract drift, failure)

Contract v3, relative to whatever v1/v2 contract you built in earlier tasks:
  - `seller_rating` is optional (present only from 2025-06-10 onward; the
    contract must not reject rows missing it before that date, and must
    still type-check it as a float in [1.0, 5.0] when present).
  - `price` must be normalized to a numeric value before the contract
    validates it, regardless of whether the raw record carried a JSON
    number or a locale-formatted string (US-style "$1,299.00" or EU-style
    "1.299,00 EUR" — see the module's schema-drift notes from your earlier
    tasks). Locale parsing belongs in a discrete, testable step — do not
    bury it inside the pandera schema itself.

Idempotency is graded per stage, not just end-to-end: re-running this DAG
for a dt that already succeeded must not change core row counts, must not
duplicate the silver-lake partition, and must not double-count the mart
row. Design your writes (upserts, overwrite-by-partition, delete-then-insert
in a single transaction, whatever) with that constraint first, then fill in
the logic.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

DAG_ID = "t10_capstone"


@task
def ingest(dt: str) -> None:
    """Read data/raw/dt=<dt>/prices.ndjson, load parseable lines into
    staging.price_records_raw, route malformed (non-JSON) lines to
    ops.quarantine with stage='ingest'. Must be safe to re-run for the same
    dt (no duplicate staging rows, no duplicate quarantine rows).
    """
    raise NotImplementedError


@task
def contract_gate(dt: str) -> None:
    """Validate staging rows for dt against the v3 contract (see module
    docstring above). Rows that fail validation go to ops.quarantine with
    stage='contract', carrying enough of the original payload and a reason
    to reconstruct why they failed. Rows that pass are the input to the
    core-load stage. If the failure rate for this dt looks like a schema
    change rather than routine bad data, fire a type='contract_drift' alert
    to the alert-sink (see harness/common.py's read_alerts() for how
    validators check this, and the module's alert-sink contract for the
    POST shape).
    """
    raise NotImplementedError


@task
def load_core(dt: str) -> None:
    """Upsert contract-passing rows for dt into core.price_records. Must be
    idempotent: re-running this task for a dt that already loaded must not
    change the row count or duplicate rows. Write an ops.load_audit row for
    this dt (dag_id, run_id, dt, rows_loaded, status, finished_at) whether
    it succeeds or fails — the audit trail should never silently skip a
    day.
    """
    raise NotImplementedError


@task
def silver_lake(dt: str) -> None:
    """Read core.price_records for dt, write it (via the embedded pyspark
    session — see dags/smoke_env.py for the s3a config block you need) as
    parquet to s3a://lake-06/silver/prices/dt=<dt>/. Overwrite that
    partition specifically on re-run — do not touch other days' partitions
    and do not append duplicate rows into this one.
    """
    raise NotImplementedError


@task
def build_mart(dt: str) -> None:
    """Aggregate core.price_records for dt by (category, currency) and
    upsert into mart.daily_category_prices (see src/ddl.sql for the target
    schema). Re-running for the same dt must leave exactly one row per
    (dt, category, currency), not accumulate duplicates.
    """
    raise NotImplementedError


@task
def summarize_and_alert(dt: str) -> None:
    """Compute this dt's quarantine rate (quarantined rows / total rows
    considered) and compare it against a threshold; fire a
    type='quarantine_rate' alert if it's abnormally high. This task should
    run even if an upstream task for this dt failed, and should fire a
    type='dag_failure' alert in that case — decide your trigger rule
    (trigger_rule=...) deliberately, don't leave it at the default.
    """
    raise NotImplementedError


@dag(
    dag_id=DAG_ID,
    schedule=None,
    start_date=datetime(2025, 6, 1),
    catchup=False,
    tags=["capstone", "t10"],
)
def t10_capstone():
    # TODO: wire logical_date -> dt string, then chain the stages above.
    # Remember: this DAG must support both a full 14-day backfill (CP1) and
    # a scoped re-run of a handful of days (CP2) without touching healthy
    # partitions outside the days it's asked to process.
    raise NotImplementedError


t10_capstone()
