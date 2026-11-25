# 04 — Poison records and alerting

## Backstory

The ingestion DAG you built earlier does its job when the scrapers behave. They don't. Truncated dumps, half-written JSON, scrapers that lose the URL mid-flight, price parsers that emit `-347.20`, a currency field that says `???` — all of it lands in the daily files, and right now anything that doesn't parse just vanishes in a `try/except`. Nobody knows how much data is being dropped, or why.

The platform team's position is simple: silent skips are unacceptable. Every line that can't make it into staging must land somewhere queryable, with a reason attached, and when the breakage rate spikes, a human must find out from an alert — not from a downstream analyst three days later. And when a whole day's dump simply never arrives, the pipeline must fail loudly, not shrug and load zero rows.

## What's given

- `src/ddl.sql` — DDL for `ops.quarantine` (new: the dead-letter table), plus idempotent re-statements of `staging.price_records_raw` and `ops.load_audit` from the earlier tasks. Apply it once:

      docker compose exec -T warehouse psql -U sandbox -d pipelines < src/ddl.sql

- `src/t04_quarantine_and_alerts.py` — DAG skeleton with the business-rule constants (allowed currencies, per-category price ceilings, quarantine reason strings, the 3% alert threshold). Copy it into the module's `dags/` directory and fill in the TODOs.
- `tests/make_drill_day.py` — deterministic drill-data builder. It derives `data/raw/dt=2025-06-15/prices.ndjson` from the 2025-06-14 file, corrupting exactly every 10th line, and prints the counts your DAG must reproduce. Given tooling: run it, don't modify it.
- `tests/_reference.py` — the classification rules in executable form, shared by the drill builder and the validator. Reading it before you've written your own `classify_line` defeats the point of the task.
- `tests/validate.py` — the validator.
- The raw dumps `data/raw/dt=2025-06-01..14/` and the alert sink at `http://alert-sink:8000/alert` (from inside the compose network), which appends every POSTed JSON body to `data/alerts/alerts.ndjson` on the host.

## What's required

A DAG `t04_quarantine_and_alerts` that evolves your ingestion logic from the earlier tasks into a load that never drops a line silently.

**Classification.** Every line of the day's file is classified independently, by its position in the file (`line_no`, 0-based):

- *Malformed* — `json.loads` fails → `ops.quarantine` with `stage='ingest'`, `reason='malformed'`, the verbatim line in `raw_line`, `payload` NULL.
- *Invalid* — parses, but violates a business rule → `ops.quarantine` with `stage='validate'`, the parsed record in `payload`, and one of these reasons (first matching rule wins, in this order):
  1. `missing_product_url` — `product_url` key absent or null.
  2. `invalid_price` — `price` is a JSON number and is `<= 0` or above the category's ceiling from `CATEGORY_PRICE_CEILING`. Non-numeric prices are *not* this task's problem — skip the price check for them.
  3. `unknown_currency` — `currency` outside {USD, EUR, GBP}.
  4. `invalid_scraped_at` — the UTC date of `scraped_at` is not the file's day.
- *Valid* — everything else → `staging.price_records_raw` keyed `(dt, line_no)`, as before.

Note what "by line" means for the exact duplicate lines that exist in the dumps: each copy has its own `line_no` and is loaded (or quarantined) separately. Deduplication is a downstream concern, not ingestion's.

**Idempotency.** Rerunning the DAG for a day must leave both staging *and* quarantine row counts for that day exactly as they were. `ops.quarantine` has no natural key, so this doesn't fall out of a primary key for free — design it.

**Alerting.**

- An end-of-run task computes the day's quarantine rate — `(malformed + invalid) / total_lines` — and POSTs a JSON alert to the sink **only** when the rate is strictly above 3%: `{"type": "quarantine_rate", "dt": ..., "rate": ..., "malformed_count": ..., "invalid_count": ..., "total_lines": ...}`.
- A DAG-level `on_failure_callback` POSTs `{"type": "dag_failure", "dag_id": ..., "run_id": ..., "dt": ...}` when any run of the DAG fails.
- A missing input file for the day is a *failure* (the file-doesn't-exist case must raise), never a zero-row success.

**The three scenario runs.** Once the DAG works, produce a clean alerts file: stop nothing, just delete `data/alerts/alerts.ndjson` and run each scenario once:

1. `airflow dags test t04_quarantine_and_alerts 2025-06-05` — a normal day, rate ~1.4%, **no** alert.
2. `uv run python tests/make_drill_day.py`, then `airflow dags test t04_quarantine_and_alerts 2025-06-15` — the drill day, rate ~11%, the `quarantine_rate` alert fires.
3. `airflow dags test t04_quarantine_and_alerts 2025-06-16` — no data directory exists for this day; the run fails and the `dag_failure` alert fires.

(All `airflow` commands via `docker compose exec airflow-scheduler ...` from the module root.)

## Completion criteria

From this task directory, with the compose stack up:

    uv run python tests/validate.py

prints `PASSED`. The validator checks, against ground truth and the reference classifier:

- per-reason quarantine counts and the staging row count for 2025-06-05 and for the drill day 2025-06-15 (staging must hold exactly the lines that are neither malformed nor invalid — duplicates included, one row per line);
- that a rerun of 2025-06-05, which the validator triggers itself via `airflow dags test`, changes no counts;
- that `data/alerts/alerts.ndjson` contains exactly one `quarantine_rate` alert (for 2025-06-15, with the rate matching the drill day's actual rate), at least one `dag_failure` alert (for 2025-06-16 only), and no alerts for 2025-06-05.

## Estimated evenings

1

## Topics to read up on

- Airflow TaskFlow API and passing data between tasks (XCom, and why it is not a data plane)
- Airflow DAG-level vs task-level failure callbacks and the callback context
- Dead-letter / quarantine table patterns in ELT
- Idempotent loads without a natural key (delete-and-insert in one transaction, synthetic keys)
- Postgres `jsonb` inserts from Python, batching strategies in psycopg 3
- Templating in Airflow (`ds`, logical date) with `schedule=None` and `dags test`
