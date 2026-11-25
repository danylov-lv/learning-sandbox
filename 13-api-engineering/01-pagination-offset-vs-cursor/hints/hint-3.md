Concrete shape, without writing the handlers for you.

**Connecting to Postgres.** The scaffold's docstring already points at
`harness.common.pg_pool` / `pg_conn`. The idiomatic FastAPI shape is a
`lifespan` context manager on the `app`: open one `pg_pool()` on startup,
stash it (e.g. `app.state.pool = pool`), and close it on shutdown; each
request then checks out a pooled connection via `with pool.connection() as
conn:` instead of paying a fresh TCP + auth round-trip per request. If that
feels like a detour before you've got the SQL working, start with a plain
`pg_conn()` per request (as the un-implemented stub's docstring says, this
is simpler and still correct) and swap in the pool once both endpoints work
-- the validator only checks behavior, not which connection strategy you
used.

**Clamping.** Decide sane bounds once, as constants, and apply them to
whatever the client sent before it touches SQL: a `limit <= 0` should not be
sent to Postgres as-is (it's nonsensical or, worse, `LIMIT -1` server-side
footguns depending on driver), and a `limit` in the millions is a
self-inflicted DoS. Clamp to a fixed floor and ceiling. For `offset`, a
negative value should not reach the query either. For `cursor`, treat
anything missing/negative/non-numeric as "start from the beginning" --
that's what makes the first page reachable without a special case in the SQL
itself (`WHERE id > 0` is already correct for "everything", since ids start
at 1).

**Building `next_cursor`.** After running the keyset query and getting back
however many rows it found: if you got a full page (exactly `limit` rows),
there might be more -- `next_cursor` is the `id` of the LAST row in that
page. If you got fewer rows than `limit` (including zero), you've drained
the catalog -- `next_cursor` is `null`. This is the one piece of state the
whole scheme needs; everything else about "where am I" lives in that single
integer, not in any server-side session.

**Response shapes.** Match the docstrings exactly -- `{"items", "limit",
"offset"}` for the OFFSET endpoint, `{"items", "next_cursor"}` for the
cursor one, each item at least `{"id", "title", "price"}` with `price` as a
JSON number (cast the `NUMERIC` column to `float`, don't return a Decimal or
a string). The validator computes its own oracle straight from
`shop.products` and compares field-by-field -- getting the SQL right and the
serialization right are equally load-bearing.
