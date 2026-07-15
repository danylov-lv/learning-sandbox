# 05 -- Streaming Large Exports

## Backstory

Ops wants a "download the catalog" button on the seller dashboard: hit an
endpoint, get the whole product catalog back as newline-delimited JSON
(NDJSON -- one JSON object per line), pipe it into whatever ETL job or
spreadsheet-import script needs it that week. The catalog is 200,000 rows
today; a filtered export (one category) is anywhere from a few hundred rows
to tens of thousands.

The first version anyone writes looks like this:

```python
rows = cur.execute("SELECT ... FROM shop.products ...").fetchall()
body = "\n".join(json.dumps(row) for row in rows)
return Response(body, media_type="application/x-ndjson")
```

It works. It also pulls every matching row into a Python list, and builds
the entire response body as one string, before the client sees a single
byte. On a laptop with SCALE=0.01 this is invisible. At the real catalog
size it is a multi-hundred-thousand-row list sitting in memory, then a
multi-tens-of-megabytes string sitting in memory right next to it, for an
endpoint that -- if this were a real service -- ten sellers could hit at
once.

The trap is that wrapping the SAME code in a `StreamingResponse` does not
fix it. `fetchall()` already forced Postgres's driver to materialize the
full result before your generator's first `yield` runs; putting a streaming
wrapper around a value that was already fully materialized is decoration,
not a fix. Genuine streaming has to hold at every layer: a server-side
cursor (or a chunked `fetchmany()` loop) pulling a bounded batch of rows
from Postgres at a time, feeding a generator that yields one line per row,
feeding an HTTP response that writes each line to the socket as it's
produced. Peak memory for serving the export should depend on your batch
size, not on how many rows the catalog happens to have.

## What's given

- `src/app.py` -- a real FastAPI `app` with the one route defined, handler
  body stubbed `raise NotImplementedError`. The module docstring spells out
  the exact query params, per-line JSON shape, ordering requirement, and
  the "no full materialization anywhere in the chain" contract.
- `tests/validate.py` -- the checker (see Completion criteria). No
  `baseline.py` for this task: unlike a timing claim, the memory check
  compares two sizes of the SAME export inside one validator run, so there
  is nothing to record ahead of time on this machine.
- The shared harness (`harness.common`, `harness.service`): `pg_conn()` for
  Postgres, `run_app()` to launch your app on a real ephemeral port,
  `measure_peak_memory()` (tracemalloc peak around a call).
- A seeded, read-only `shop` schema (Postgres, port 54312) with 200,000
  products. **Never write to `shop`.**

## What's required

Implement `GET /export/products` in `src/app.py`:

- Optional query param `category_id: int`. Omitted -> export every row in
  `shop.products`. Present -> export only that leaf category's rows.
- Rows ordered by `id` ASCENDING (Postgres can walk the primary key index
  for this -- no separate sort/materialize step).
- Response: HTTP 200, `media_type="application/x-ndjson"`, body = one JSON
  object per line (`\n`-terminated), no wrapping array. Each line has
  exactly these keys: `id`, `seller_id`, `category_id`, `title`, `price`,
  `in_stock`, `created_at` (ISO 8601 string).
- An empty/unmatched `category_id` is a valid response (empty body, HTTP
  200), not an error.
- The generator behind the `StreamingResponse` may be sync or async --
  Starlette runs a sync generator in its threadpool automatically, so a
  plain `def` generator using the harness's synchronous `pg_conn()` is a
  legitimate, non-hacky choice. What's graded is that it streams: a bounded
  batch fetched, its lines yielded, the next batch fetched -- never the
  whole result via one call.
- Close what you open. Scope the cursor/connection with `with` inside the
  generator so a client disconnect or generator exhaustion doesn't leak a
  connection.

Full parameter/response contract, including the exact per-row JSON shape,
is in `src/app.py`'s docstring -- read it before starting.

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

The validator:

- Launches your app on a real ephemeral port (a real socket matters here --
  see `tests/validate.py`'s module docstring for why).
- Drains `GET /export/products?category_id=<a small leaf category>` and
  checks row **count**, id **checksum**, and price **sum** against its own
  oracle computed with independent SQL against `shop.products` -- never
  trusting your app's numbers. It also checks ids arrive strictly
  increasing.
- Drains the full, unfiltered export and checks the same three things
  against the committed ground truth for the whole catalog.
- **The memory check**: both drains are measured with `measure_peak_memory`
  (tracemalloc peak). The full export is roughly 300x more rows than the
  small one. A real streaming chain holds a bounded batch regardless of
  total rows, so peak memory should barely move between the two sizes; an
  implementation that materializes the result (`fetchall()`, or building
  the whole body as one string/list, with or without a `StreamingResponse`
  wrapper around it) allocates roughly proportional to row count. The
  validator asserts the peak-memory ratio between the two sizes stays under
  a threshold set well below the row-count ratio -- a materializing
  implementation blows through it by a wide margin, a real one clears it
  with room to spare.

It prints `PASSED` with both row counts and the observed peak-memory ratio,
or `NOT PASSED: <reason>` and exits 1.

## Estimated evenings

1

## Topics to read up on

- Generators and lazy iteration in Python (`yield`, `fetchmany()` loops)
  vs. eagerly building a list
- Server-side ("named") cursors in Postgres/psycopg -- what actually stops
  the whole result from being materialized server-side
- `StreamingResponse` / chunked transfer encoding -- what the client
  actually receives, and when a "streaming" wrapper does nothing
- `tracemalloc` and peak-memory profiling -- what it measures (traced
  Python allocations) vs. what it doesn't (native buffers, OS-level RSS)
- Backpressure: what happens when the producer (your generator) is faster
  than the consumer (the client reading the socket)

## Off-limits

`.authoring/design.md` (at the module root) documents the harness API, the
`shop` schema, the committed ground truth, and the verification philosophy
for every task in this module -- spoilers. Don't read it before finishing.
