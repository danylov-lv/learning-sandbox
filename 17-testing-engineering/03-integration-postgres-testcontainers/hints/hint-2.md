Mechanisms for each of the four properties, without code:

**Idempotency.** Build a list of 2-3 observation dicts (`product_url`,
`scraped_at`, `price`, `currency`). Call `upsert_observations(conn, rows)`.
Then build a SECOND list with the SAME `product_url`/`scraped_at` pairs but
a DIFFERENT `price` (and maybe `currency`), and call
`upsert_observations(conn, rows2)`. Now read the table back (via
`load_incremental` with a `since` older than everything, or a raw
`SELECT COUNT(*)` through the same `conn` if you want to check row count
directly). Two things must both hold: the row count equals the number of
distinct keys (not double), and the price/currency values match the
SECOND call, not the first.

**Durability.** `tests/conftest.py`'s `conn` fixture gives you one
connection per test via `postgres_dsn`. Nothing stops your test from
opening a SECOND one: `psycopg.connect(postgres_dsn)` (the fixture is a
plain string DSN, request it as a second fixture argument alongside
`conn`). Write through `conn`, then query through the second connection,
then close it. If the second connection sees zero rows, the write never
actually committed.

**Watermark boundary.** Pick a concrete `datetime` (timezone-aware --
the column is `timestamptz`) and insert one row with `scraped_at` set to
exactly that value, plus at least one row strictly before and one strictly
after. Call `load_incremental(conn, since=<that exact value>)` and check
the boundary row's key is NOT in the result, while the strictly-after
row's key IS.

**Pagination completeness.** Insert enough rows (say 5-7) that a small
`limit` (say 2) needs 3+ calls to `page` to exhaust them. Track `after =
None` initially; after each call, if you got rows back, set `after` to
`(last_row["scraped_at"], last_row["id"])` and call `page` again; stop
when a call returns fewer rows than `limit` (or zero). Collect every row's
`id` you ever saw across all calls into a list, then assert that list --
as a *set* -- equals the full set of ids you inserted, AND that the list
has no duplicates (`len(list) == len(set(list))`). Both checks matter:
duplicates alone won't show up if you only check the set.
