# Hint 3

A stage-by-stage walkthrough in pseudocode. This is the shape of a working
solution, not the code — every line still has design decisions left in it.

```
DAG t10_capstone, schedule=None (you drive it via `dags test` / backfill)

dt = logical_date formatted as YYYY-MM-DD

ingest(dt):
    open /opt/sandbox/data/raw/dt=<dt>/prices.ndjson
    in one transaction:
        delete staging rows for dt; delete quarantine rows for (dt, 'ingest')
        for each line (numbered):
            try json.loads -> insert (dt, line_no, payload) into staging
            except -> insert quarantine row (dt, 'ingest', reason, raw_line)

contract_gate(dt):
    read staging payloads for dt
    normalize price on every record (plain number | US string | EU string)
      -> unparseable price = contract failure, reason='price_unparseable'
    validate v3: required keys incl. currency; seller_rating optional,
      float in [1.0,5.0] when present; scraped_at inside [dt, dt+1)
    in one transaction:
        delete quarantine rows for (dt, 'contract'); insert failures
    if failure_rate(dt) >> baseline and one reason dominates:
        POST alert {"type": "contract_drift", "dt": dt, "reason": ...,
                    "failed": n, "total": m}
    hand passing records (with normalized numeric price) to the next stage
      (XCom a temp-table name / staging flag column, NOT the records
       themselves — 40k records through XCom is the wrong tool)

load_core(dt):
    INSERT ... ON CONFLICT (source_site, product_url, scraped_at) DO NOTHING
    insert ops.load_audit row (dag_id, run_id, dt, rows_loaded, status, now())

silver_lake(dt):
    spark session (copy the s3a config block from dags/smoke_env.py)
    df = spark.read via JDBC or via a psycopg export you parquet yourself —
      either is fine; the check only cares about the partition's row count
    df.write.mode("overwrite").parquet(f"s3a://lake-06/silver/prices/dt={dt}/")

build_mart(dt):
    one SQL statement: insert-select from core.price_records for this dt,
      grouped to the mart's (dt, category, currency) grain with the four
      aggregates from src/ddl.sql, upserting on the mart PK

summarize_and_alert(dt):   # trigger_rule that fires even on upstream failure
    rate = quarantined(dt) / total_lines(dt)
    if rate > threshold: POST {"type": "quarantine_rate", "dt": dt, "rate": rate}
    if any upstream task failed: POST {"type": "dag_failure", "dt": dt, ...}
```

CP2 drills:

- `drill_break_midstate` deletes mart rows + silver partitions for
  2025-06-03/07/11 but leaves core intact. Recovery does NOT need to
  re-ingest: if your DAG stages are cleanly separated you can re-run just
  the three days end-to-end (core's ON CONFLICT DO NOTHING makes the
  re-ingest a no-op on data) — but check what your core upsert does to
  loaded_at on conflict before choosing DO UPDATE. The validator compares
  unaffected days' max(loaded_at) against the pre-drill snapshot.
- `drill_new_drift` plants dt=2025-06-15 where ~40% of records renamed
  `currency` -> `currency_code`. Run the pipeline for 06-15 normally. If
  your contract treats a missing `currency` as a per-record failure (not
  a task crash), the ~60% load fine, the rest land in quarantine with one
  dominant reason, and your drift heuristic fires the alert. If instead
  your task hard-crashes on the first bad record, that is the bug this
  drill exists to expose.
