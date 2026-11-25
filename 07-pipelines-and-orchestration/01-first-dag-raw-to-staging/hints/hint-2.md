Two viable ways to get the logical date inside `load_day`:

1. `from airflow.sdk import get_current_context`, call it inside the task
   body, then read the date off the context object it returns (it's a
   mapping-like object — the key you want corresponds to what used to be
   called `ds` in classic Airflow: a `YYYY-MM-DD` string).
2. Declare a parameter on `load_day` whose name matches a context key Airflow
   knows how to inject into TaskFlow tasks automatically (again, `ds` is the
   short-string-date one). Airflow inspects the function signature and fills
   in matching names for you — no explicit `**context` needed.

Either works; pick one and be consistent. Don't reach for `datetime.now()`
or an environment variable — both defeat the point of a logical date.

For the file read: open the day's `prices.ndjson` with `encoding="utf-8"`,
iterate with `enumerate(f, start=1)` so the loop variable is already your
1-based `line_no`, `try: json.loads(line)` per line, `except
json.JSONDecodeError: skip and count`. Collect `(dt, line_no, payload)`
tuples for everything that parses, then hand the whole batch to
`cur.executemany("INSERT INTO staging.price_records_raw (dt, line_no,
payload) VALUES (%s, %s, %s)", batch)` — psycopg needs the payload adapted to
jsonb (look at `psycopg.types.json.Jsonb` or equivalent for wrapping a Python
dict before it goes into an execute call).
