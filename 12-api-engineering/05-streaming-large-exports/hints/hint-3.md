Concrete shape, without writing the handler for you.

**Pick one batching mechanism and commit to it.** Two idiomatic options,
both satisfy the "bounded batch at a time" requirement:

- A psycopg3 named cursor: `conn.cursor(name=<unique-string>)`, then either
  loop `cur.fetchmany(EXPORT_BATCH_SIZE)` until it returns an empty list, or
  set `cur.itersize = EXPORT_BATCH_SIZE` and just `for row in cur: ...` --
  psycopg fetches in batches under the hood either way once the cursor is
  named. The name has to be unique per request (concurrent requests can't
  share a server-side cursor name) -- something like a `uuid4` string is
  simplest; you don't need it to be meaningful, just collision-free.
- A plain (unnamed) cursor driven by your own keyset loop: track the last
  `id` seen, run `WHERE id > %s ORDER BY id LIMIT %s` repeatedly with
  `EXPORT_BATCH_SIZE`, stop when a batch comes back shorter than the limit.
  This is more code but has no cursor-lifetime subtleties to reason about --
  each query is a fresh, complete round-trip.

Either way, the query needs the optional `category_id` filter folded in
conditionally (build the `WHERE` clause and params list based on whether
`category_id` was passed, rather than always filtering on a possibly-`None`
value) and `ORDER BY id ASC` always present, since ordering is part of the
graded contract and the primary key index is what makes it cheap.

**Where the connection and cursor live.** Open the connection AND the
cursor *inside* the generator function, not in the route handler and not at
module scope -- the generator's body doesn't start running until Starlette
starts pulling from it, so anything opened before the generator is defined
(e.g. in the `async def` route itself, before constructing the generator)
would open a connection per request regardless of whether the client ever
reads the body. Scope both with `with` (or `try`/`finally`) so a client
disconnecting mid-stream, or the generator simply running out of rows,
still closes the cursor and returns the connection -- a generator that
never reaches its own cleanup code on early exit is a real connection leak
under real traffic. If a request never gets far enough to matter here (a
client that disconnects immediately), `pg_conn()` per request is simpler
correctness-wise than trying to share a pool across requests inside a
generator; optimize connection reuse only after the streaming behavior
itself is verified.

**Building each line.** Per row, construct a plain dict with exactly the
seven contract keys, then `json.dumps(...)` it plus `"\n"`, and `yield` the
resulting string (or `.encode()` it -- `StreamingResponse` accepts both str
and bytes chunks, just don't mix within one response). Two serialization
traps `fetchall()`'s implicit paths tend to paper over once you're
constructing dicts by hand: the `price` column comes back as a `Decimal`
from psycopg (NUMERIC columns aren't auto-cast to float) -- `json.dumps`
raises on a bare `Decimal`, so cast it explicitly (`float(row.price)`)
before it reaches the dict. `created_at` comes back as a `datetime` --
`json.dumps` raises on that too, so call `.isoformat()` explicitly rather
than relying on a default encoder.

**Wiring it to the route.** The `async def` route function itself stays
thin: parse/validate `category_id`, construct the generator (calling a
generator function doesn't run its body -- it just returns an iterator),
and `return StreamingResponse(that_generator, media_type="application/x-ndjson")`.
Whether the generator function itself is `def` (sync, using the harness's
synchronous `pg_conn()`/cursor directly -- Starlette offloads a sync
generator to its threadpool automatically) or `async def` (requiring an
async-capable path to Postgres) is your call; the docstring in `src/app.py`
already flags the sync path as legitimate and non-hacky here.

**Sanity-checking before running the validator.** Hit the endpoint with
curl/httpie against a small `category_id` and eyeball a few lines by hand --
valid JSON per line, the right seven keys, ids visibly ascending. That
catches shape bugs cheaply, before paying for a 200k-row validator run that
also happens to be timing your memory profile.
