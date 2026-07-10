# Hint 3

Rough shape (pseudocode, fill in real parsing/SQL yourself):

```
@task(retries=2, retry_delay_seconds=5)
def read_day_file(dt):
    path = raw_day_file(dt)   # from harness.common, or your own equivalent
    return path.read_text(encoding="utf-8").splitlines()

@task
def parse_lines(lines):
    out = []
    for i, line in enumerate(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append((i, payload))
    return out

@task(retries=3, retry_delay_seconds=3)
def load_records(dt, parsed_records):
    with psycopg.connect(...) as conn:
        with conn.cursor() as cur:
            for line_no, payload in parsed_records:
                cur.execute(
                    "insert into staging.price_records_raw (dt, line_no, payload, loaded_at) "
                    "values (%s, %s, %s, now()) "
                    "on conflict (dt, line_no) do update set payload = excluded.payload, loaded_at = excluded.loaded_at",
                    (dt, line_no, json.dumps(payload)),
                )
        conn.commit()
    return len(parsed_records)

@task
def write_audit_row(dt, run_id, rows_loaded, status):
    ...  # insert into ops.load_audit

@flow(name="incremental-load")
def incremental_load(dt):
    lines = read_day_file(dt)
    parsed = parse_lines(lines)
    rows_loaded = load_records(dt, parsed)
    write_audit_row(dt, run_id=str(uuid.uuid4()), rows_loaded=rows_loaded, status="success")
```

For `COMPARISON.md`: after you've run both the task 02 DAG and this flow at
least once each, sit down and actually diff your own experience — e.g. how
many `docker compose` services had to be healthy before you could see a
single successful run in each, and how long that took the first time versus
every time after.
