"""t04_quarantine_and_alerts — skeleton.

Copy this file into the module's dags/ directory before running it:

    cp src/t04_quarantine_and_alerts.py ../dags/

Then iterate with:

    docker compose exec airflow-scheduler airflow dags test t04_quarantine_and_alerts 2025-06-05

Raw input for a given logical date lives at (inside the airflow containers):

    /opt/sandbox/data/raw/dt=<YYYY-MM-DD>/prices.ndjson

Fill in every TODO. Do not change the constants below — the validator holds
you to these exact reason strings, ceilings, and threshold.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import dag, task

RAW_DIR = "/opt/sandbox/data/raw"

ALLOWED_CURRENCIES = {"USD", "EUR", "GBP"}

# Per-category "this price is absurd" ceiling. A price at or below the ceiling
# for its category is plausible; strictly above it is not. Treat this as a
# fixed business rule handed down by the pricing team, not something to derive
# statistically.
CATEGORY_PRICE_CEILING = {
    "electronics": 9730,
    "home-goods": 2290,
    "kitchen": 1410,
    "toys": 1000,
    "sporting-goods": 2800,
    "office-supplies": 470,
    "beauty": 630,
    "grocery": 200,
    "pet-supplies": 570,
    "tools": 2030,
    "furniture": 16070,
    "apparel": 1210,
}

ALERT_SINK_URL = "http://alert-sink:8000/alert"
WAREHOUSE_CONNINFO = "postgresql://sandbox:sandbox@warehouse:5432/pipelines"

QUARANTINE_RATE_THRESHOLD = 0.03

# Quarantine reason strings the validator expects, verbatim:
#   stage='ingest',   reason='malformed'            -- json.loads failed
#   stage='validate', reason='missing_product_url'
#   stage='validate', reason='invalid_price'
#   stage='validate', reason='unknown_currency'
#   stage='validate', reason='invalid_scraped_at'


def classify_line(raw_line: str, dt: str):
    """Classify one raw NDJSON line for the day `dt` ('YYYY-MM-DD').

    Return, e.g.:
        ("malformed", None)              -- json.loads failed
        ("invalid", reason, record)      -- parseable, violates a business rule
        ("valid", record)                -- parseable and clean

    Business rules, applied in this fixed order (first hit wins):

    1. missing_product_url: "product_url" key absent, or its value null.
    2. invalid_price: "price" is a JSON number and either <= 0 or strictly
       greater than CATEGORY_PRICE_CEILING[record["category"]]. If "price"
       is not a JSON number, skip this check entirely — string prices are a
       schema-drift problem for a later task, not this one.
    3. unknown_currency: "currency" not in ALLOWED_CURRENCIES.
    4. invalid_scraped_at: the UTC calendar date of "scraped_at" != dt.

    TODO: implement.
    """
    raise NotImplementedError


@task
def ingest(dt: str) -> dict:
    """Single pass over the day's raw file: classify every line, load the
    valid lines into staging.price_records_raw, the rest into ops.quarantine,
    and record the run in ops.load_audit — all against the warehouse.

    Requirements:
    - If the raw file for dt does not exist, raise — this task must FAIL
      (not skip, not succeed with zero rows) so the failure callback fires.
    - Valid lines -> staging.price_records_raw keyed (dt, line_no), where
      line_no is the 0-based position in the raw file. Idempotent on rerun.
    - Malformed lines -> ops.quarantine(stage='ingest', reason='malformed',
      raw_line=<the line verbatim>, payload=NULL).
    - Invalid records -> ops.quarantine(stage='validate', reason=<rule>,
      raw_line=<the line>, payload=<parsed record as jsonb>).
    - ops.quarantine has no natural unique key, so reruns need an explicit
      idempotency strategy (e.g. delete this dt's rows before re-inserting,
      in the same transaction).
    - Every line is classified independently: exact duplicate lines exist in
      the input and each occupies its own line_no, so a duplicated valid line
      produces two staging rows, a duplicated invalid line two quarantine
      rows. Do not dedupe here.
    - Return a small summary dict for the downstream rate check, e.g.
      {"dt": dt, "total_lines": ..., "malformed": ..., "invalid": ...}.
      Do NOT return the record lists themselves — XCom goes through the
      metadata database and is not a data plane.

    TODO: implement (psycopg; batch the inserts — ~50k single-row INSERT
    round trips will crawl).
    """
    raise NotImplementedError


@task
def check_quarantine_rate(summary: dict):
    """Compute (malformed + invalid) / total_lines from the summary. If the
    rate is strictly above QUARANTINE_RATE_THRESHOLD, POST one alert to
    ALERT_SINK_URL with at least:

        {"type": "quarantine_rate", "dt": ..., "rate": <float>,
         "malformed_count": ..., "invalid_count": ..., "total_lines": ...}

    At or below the threshold: no POST at all.

    TODO: implement (stdlib urllib is enough; see dags/smoke_env.py).
    """
    raise NotImplementedError


def on_dag_failure(context):
    """DAG-level failure callback. POST an alert to ALERT_SINK_URL with at
    least:

        {"type": "dag_failure", "dag_id": ..., "run_id": ..., "dt": ...}

    dag_id / run_id / logical date are all reachable from `context`. Keep it
    synchronous and dependency-light — it runs when the DAG is already in a
    bad state.

    TODO: implement.
    """
    raise NotImplementedError


@dag(
    dag_id="t04_quarantine_and_alerts",
    schedule=None,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    on_failure_callback=on_dag_failure,
    tags=["poison-records", "alerting"],
)
def t04_quarantine_and_alerts():
    # TODO: wire ingest -> check_quarantine_rate. The day being processed
    # must come from the run's logical date (the `{{ ds }}` template or the
    # task context), never a hardcoded string.
    raise NotImplementedError


t04_quarantine_and_alerts()
