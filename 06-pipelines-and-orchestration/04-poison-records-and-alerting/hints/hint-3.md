# Hint 3

Full shape of a working solution, in pseudocode. If your structure differs, fine — the validator only cares about the observable results.

```
classify_line(raw_line, dt):
    try record = json.loads(raw_line)
    except -> ("malformed", None)

    if "product_url" not in record or record["product_url"] is None:
        -> ("invalid", "missing_product_url", record)

    price = record.get("price")
    if price is a number (int/float, NOT bool):
        ceiling = CATEGORY_PRICE_CEILING.get(record.get("category"))
        if price <= 0 or (ceiling and price > ceiling):
            -> ("invalid", "invalid_price", record)

    if record.get("currency") not in ALLOWED_CURRENCIES:
        -> ("invalid", "unknown_currency", record)

    parse record["scraped_at"] as ISO-8601 (fromisoformat after replacing
    the trailing "Z" with "+00:00"); if it fails to parse, or its UTC date
    != dt -> ("invalid", "invalid_scraped_at", record)

    -> ("valid", record)

ingest(dt="{{ ds }}"):
    path = RAW_DIR / f"dt={dt}" / "prices.ndjson"
    if not path.exists(): raise FileNotFoundError(path)   # scenario 3

    walk the file once with enumerate(f):
        bucket each line into valid / malformed / invalid lists,
        remembering line_no and (for invalid) the reason

    one psycopg connection, one transaction:
        DELETE FROM ops.quarantine WHERE dt = %s
        executemany INSERT quarantine (dt, stage, reason, raw_line, payload)
            - malformed: ('ingest', 'malformed', line, NULL)
            - invalid:   ('validate', reason, line, Jsonb(record))
        for staging: executemany
            INSERT ... VALUES (%s, %s, %s::jsonb) ON CONFLICT (dt, line_no) DO NOTHING
            (or COPY into a temp table + INSERT ... SELECT ... ON CONFLICT)
        INSERT INTO ops.load_audit (dag_id, run_id, dt, rows_loaded, status)
        commit

    return {"dt": dt, "total_lines": n, "malformed": m, "invalid": i}

check_quarantine_rate(summary):
    rate = (summary["malformed"] + summary["invalid"]) / summary["total_lines"]
    if rate > QUARANTINE_RATE_THRESHOLD:
        POST {"type": "quarantine_rate", "dt": ..., "rate": rate,
              "malformed_count": ..., "invalid_count": ..., "total_lines": ...}

on_dag_failure(context):
    dt = str(context["logical_date"])[:10]   # or dag_run.logical_date
    POST {"type": "dag_failure", "dag_id": context["dag"].dag_id,
          "run_id": context["run_id"], "dt": dt}
    (wrap the POST in try/except — a broken alert must not mask the
     original failure in the logs)

dag body:
    check_quarantine_rate(ingest(dt="{{ ds }}"))
```

Two classic traps this pseudocode already avoids:

- `isinstance(True, int)` is `True` in Python — exclude bools explicitly when checking that `price` is a number, or a boolean price would sneak past.
- The delete-then-insert for quarantine and the staging upsert live in the *same* transaction as the audit row, so a mid-run crash can't leave the day half-loaded with no trace.
