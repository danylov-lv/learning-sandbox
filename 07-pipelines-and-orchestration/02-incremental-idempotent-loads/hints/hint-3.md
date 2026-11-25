Rough shape of `load_partition` (delete-then-insert variant; upsert only
changes the write step):

```
day = <logical date as YYYY-MM-DD string, from context>
run_id = <run_id from context, e.g. get_current_context()["run_id"]>
path = f"{RAW_DIR}/dt={day}/prices.ndjson"

parse the file exactly like task 01: build `batch` of (day, line_no, payload),
count `skipped`

conn = psycopg.connect(WAREHOUSE_DSN)
try:
    with conn:  # psycopg3: `with conn` commits on clean exit, rolls back on exception
        with conn.cursor() as cur:
            cur.execute("DELETE FROM staging.price_records_raw WHERE dt = %s", (day,))
            cur.executemany(
                "INSERT INTO staging.price_records_raw (dt, line_no, payload) VALUES (%s, %s, %s)",
                batch,
            )
            cur.execute(
                "INSERT INTO ops.load_audit (dag_id, run_id, dt, rows_loaded, status) "
                "VALUES (%s, %s, %s, %s, 'success')",
                (DAG_ID, run_id, day, len(batch)),
            )
except Exception:
    with psycopg.connect(WAREHOUSE_DSN) as failure_conn:
        with failure_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ops.load_audit (dag_id, run_id, dt, rows_loaded, status) "
                "VALUES (%s, %s, %s, 0, 'failed')",
                (DAG_ID, run_id, day),
            )
    raise
finally:
    conn.close()

return {"rows_loaded": len(batch), "skipped": skipped}
```

Note the delete, the insert batch, and the audit-success row are all inside
the *same* `with conn:` block — that's what makes "delete the day, reload
it, record success" one atomic unit. If the audit insert were in a separate
transaction after a commit, a crash between the two would leave you with
correct data and a missing audit row, which is a smaller bug than data
corruption but still not what "one row per run" promised.
