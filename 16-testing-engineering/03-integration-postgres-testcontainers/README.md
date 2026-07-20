# 03 -- Integration testing against Postgres (testcontainers)

## Backstory

Your scraper's price history lives in Postgres, behind a small
`PriceRepo` data-access layer: upsert a batch of observations, load
everything since a watermark, page through the table. Someone on the team
mocked `psycopg` in the unit tests for this layer months ago -- every test
was green, the mocks returned exactly what the assertions expected, and
the suite caught nothing when a teammate later swapped `ON CONFLICT
DO UPDATE` for `DO NOTHING` while "simplifying" the upsert. Stale prices
sat in the table for two weeks before anyone noticed, because the mock had
no idea what `ON CONFLICT` even means -- it was never asked to understand
SQL, only to return canned data.

This task is that fix: test the DAO against a REAL, ephemeral Postgres
instance, so `ON CONFLICT`, transaction commits, and ordering are actually
exercised by the database engine, not simulated by whatever you assumed
the database would do.

## What's given

- `src/impl.py` -- a correct, complete `PriceRepo` (do not edit). Read the
  docstring on every method; it's the contract your tests check.
- `src/sut.py` -- generated shim. Your tests import `from src.sut import
  PriceRepo`, never `from src.impl import ...` -- that indirection is how
  grading swaps in a mutant implementation without changing your test
  file.
- `tests/conftest.py` -- a session-scoped `PostgresContainer("postgres:16")`
  fixture (`postgres_dsn`) plus a function-scoped `conn` fixture that
  hands each test a fresh `psycopg` connection against a clean,
  freshly-created `observations` table. You should not need to edit this
  file; it exists so you spend your time on assertions, not container
  boilerplate.
- `tests/test_repo.py` -- your deliverable, currently a stub with TODOs
  and no active tests.
- `hints/` -- three hints, direction to concrete approach, if you get
  stuck.
- Docker Desktop must be running. This task starts a real container per
  `pytest` run; there is no way around that here -- that's the point.

`.authoring/` is off-limits -- it documents the specific bugs your suite
is graded against. Reading it before finishing defeats the exercise.

## What's required

Write integration tests in `tests/test_repo.py` against `PriceRepo`,
using the `conn` fixture. At minimum, cover:

- **Upsert idempotency.** Upserting the same rows twice must not create
  duplicate rows, and the second upsert's values (not the first's) must be
  what's in the table afterward.
- **Durability.** A write made through one connection must be visible
  through a DIFFERENT connection against the same database -- open a
  second connection in your test rather than trusting reads through the
  same connection that wrote the data.
- **Watermark boundary.** `load_incremental(conn, since)` must exclude a
  row whose `scraped_at` is exactly `since`, and include everything
  strictly after it.
- **Pagination completeness.** Walking `page(conn, after, limit)` across
  multiple pages (feeding each page's last row's cursor back in) must
  visit every row exactly once -- no gaps, no duplicates at page
  boundaries, including when rows share the same `scraped_at`.

Your suite is graded by whether it would catch a real regression in any
of the above, not by code coverage or how many tests you write. A test
that always passes regardless of what `PriceRepo` does is worth nothing
here.

## Completion criteria

Docker Desktop must be running. Run from the **module root**:

```bash
uv run python 03-integration-postgres-testcontainers/tests/validate.py
```

This runs your suite against the correct `PriceRepo` (must fully pass,
collecting at least 4 tests), then against a bank of mutated
implementations, each with exactly one injected bug (wrong `ON CONFLICT`
target, a dropped commit, an off-by-one in pagination or the watermark
comparison, ...). Your suite must FAIL against every mutant -- a mutant
your suite still passes against means that regression would ship
undetected.

Prints `PASSED` / `killed N/N mutants` and exits 0, or `NOT PASSED:
<reason>` and exits 1. Each mutant run starts its own container (via the
session fixture, one per `pytest` subprocess), so a full grading pass
takes a few minutes -- that's expected.

## Estimated evenings

2

## Topics to read up on

- Integration testing vs. unit testing: what a mock can never catch about
  a real SQL engine's behavior
- `testcontainers` lifecycle: session-scoped vs. function-scoped fixtures,
  what "one container per pytest run" buys you vs. costs you
- Idempotent upsert via `INSERT ... ON CONFLICT (...) DO UPDATE`
- Keyset (cursor-based) pagination vs. offset pagination, and why keyset
  needs a full tiebreak column to be well-defined under ties
- Watermark / incremental-load patterns and strict vs. inclusive boundary
  semantics
- `psycopg` (v3) connections, cursors, and transaction/commit semantics
- Why "the mock returned what I told it to return" is not the same claim
  as "the database does what I think it does"
