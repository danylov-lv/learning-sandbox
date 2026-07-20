Start by actually running the fixture and poking at `PriceRepo` from a
throwaway script or a Python REPL before writing any `assert`. Import
`from src.sut import PriceRepo`, get a connection the same way
`tests/conftest.py`'s `conn` fixture does (`psycopg.connect(dsn)` against a
`PostgresContainer("postgres:16")`), call `create_schema`, then
`upsert_observations` with a couple of rows, and just print what
`load_incremental` and `page` give back. Get comfortable with the shapes
before you start asserting on them.

Then think about each of the four required-coverage bullets in the README
as a question about STATE CHANGE, not about a single call's return value:

- Idempotency isn't "does upsert not crash" -- it's "if I call it twice
  with the same input, is the *second* call's effect the one that sticks,
  and is the row count unchanged?" That means your test needs to call
  `upsert_observations` at least twice with overlapping keys and check
  what's in the table afterward, not just that the call returned.
- Durability isn't testable from the same connection that wrote the data
  -- a connection can always see its own uncommitted writes. You need a
  second, independent connection to prove a write actually committed.
- A boundary test needs a row placed at EXACTLY the watermark value you
  pass in, not just "some rows before, some after." Construct that row on
  purpose.
- Pagination completeness is a property of the WHOLE walk, not any single
  page. Insert enough rows that a `limit` you choose forces at least two
  or three pages, then walk until a page comes back empty (or shorter than
  `limit`), collecting every row's identity as you go, and check the
  collected set against what you inserted.

You don't need many tests to hit all four -- four to eight well-aimed
tests, each checking a specific property, will get you further than a
long list of shallow "doesn't crash" tests.
