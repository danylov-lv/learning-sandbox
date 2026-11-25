Rough shape of `load_day`:

```
day = <read logical date from context as a YYYY-MM-DD string>
path = f"{RAW_DIR}/dt={day}/prices.ndjson"

batch = []
skipped = 0
with open(path, encoding="utf-8") as f:
    for line_no, line in enumerate(f, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        batch.append((day, line_no, Jsonb(payload)))

connect to warehouse with psycopg
open a cursor, executemany the insert over `batch`
commit
log skipped count
return {"rows_loaded": len(batch), "skipped": skipped}
```

If you'd rather use `COPY` instead of `executemany`, the shape is the same
up through building `batch`; only the last step (how you get rows into
Postgres) changes — `copy.write_row` per tuple inside a
`cursor.copy("COPY staging.price_records_raw (dt, line_no, payload) FROM
STDIN")` block, with the payload serialized to a JSON string yourself before
writing it (COPY doesn't auto-adapt Python dicts the way execute-family
calls do).

Don't try to hold the whole file in memory as a giant list of parsed
objects if you're worried about the ~40-60k lines/day volume — building
`batch` incrementally and executing once at the end is already fine at this
scale; you do not need to chunk into multiple `executemany` calls for this
task.
