"""s12.t05 -- streaming large exports.

An "export the catalog" endpoint for the marketplace's ops/seller dashboard:
`GET /export/products` writes the whole `shop.products` table (optionally
filtered to one category) out as newline-delimited JSON (NDJSON, one JSON
object per line). The catalog is 200,000 rows; a filtered export can still
be tens of thousands.

The obvious first implementation is:

    rows = cur.execute("SELECT ... FROM shop.products ...").fetchall()
    body = "\n".join(json.dumps(row) for row in rows)
    return Response(body, media_type="application/x-ndjson")

This WORKS, and it is exactly what you must not ship. `fetchall()` pulls
every matching row into a Python list before a single byte goes out, and
`"\n".join(...)` builds the entire response body as one string in memory.
Wrapping that same `body` in a `StreamingResponse` does not help either --
the expensive part already happened before the wrapper ever ran; a
`StreamingResponse` around a `fetchall()` buys you nothing. Peak memory for
this endpoint must grow with the ROWS YOU HOLD AT ONCE, not with the rows
you eventually send -- which means the chain has to stream at every layer:
a server-side cursor (or chunked `fetchmany()` loop) pulling a bounded
number of rows from Postgres at a time, feeding a generator that yields one
NDJSON line at a time, feeding a `StreamingResponse` that writes each line
to the client as it is produced. None of the three layers may buffer the
whole result.

Contract the validator depends on:

- `GET /export/products` — optional query param `category_id: int`. With no
  `category_id`, export every row in `shop.products`. With `category_id`,
  export only rows in that leaf category. Either way, rows are ordered by
  `id` ASCENDING (the table's primary key -- Postgres can walk this via the
  index without a separate sort/materialize step, which matters for the
  "no full materialization anywhere in the chain" requirement above).
- Response is `media_type="application/x-ndjson"`, HTTP 200, body = one JSON
  object per line, `\n`-terminated, no wrapping array, no trailing commas --
  a lone JSON document per line, in `id` order, so a client can process the
  export by reading line-by-line without ever holding the whole response in
  memory either.
- Each line is a JSON object with EXACTLY these keys (types matter -- the
  validator parses every line):
  - `id` (int)
  - `seller_id` (int)
  - `category_id` (int)
  - `title` (string)
  - `price` (number)
  - `in_stock` (bool)
  - `created_at` (string, ISO 8601 -- `datetime.isoformat()` is fine)
- An unknown/empty `category_id` (no matching rows) is a valid response: an
  empty body, HTTP 200 -- not an error.
- The generator you pass to `StreamingResponse` may be sync (a plain `def`
  with `yield`) or async (`async def` with `yield`) -- Starlette runs a sync
  generator in its threadpool automatically, so a sync generator using the
  harness's synchronous `pg_conn()` is a perfectly legitimate choice here,
  not a hack. What matters is that IT streams: fetch a bounded batch, yield
  the lines for that batch, fetch the next batch -- never the whole result
  in one call.
- Close what you open. The cursor and connection must not leak if the
  client disconnects mid-stream or the generator runs to completion --
  scope them with `with`/`try`-`finally` inside the generator itself, not
  at module import time (a module-level connection held across requests
  would defeat the point and also isn't safe to share across concurrent
  requests).

Reaching Postgres: `harness.common.pg_conn()` gives you a live psycopg (v3)
connection (the module root is on `sys.path` when this app is launched by
the validator). psycopg's named/server-side cursors
(`conn.cursor(name="...")`) or a plain cursor driven with repeated
`fetchmany(BATCH_SIZE)` calls are the two idiomatic ways to pull bounded
batches instead of `fetchall()` -- pick either.

`EXPORT_BATCH_SIZE` below is a suggested batch size for whichever chunking
approach you use; it is not part of the graded contract (the validator does
not inspect it), just a reasonable default to start from.
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

EXPORT_BATCH_SIZE = 2000

app = FastAPI(title="s12.t05 streaming large exports")


@app.get("/export/products")
async def export_products(category_id: int | None = None):
    """Stream `shop.products` (optionally filtered to `category_id`) as
    NDJSON, ordered by `id` ascending, without ever materializing the full
    result set or the full response body in memory.

    See the module docstring above for the exact per-line JSON shape and
    the streaming requirement (server-side cursor / chunked fetch feeding a
    generator feeding a `StreamingResponse` -- no `fetchall()`, no building
    the whole body as one string first).
    """
    raise NotImplementedError
