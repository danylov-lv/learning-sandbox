"""YOUR DELIVERABLE -- integration tests for `PriceRepo` against a real Postgres.

Read `src/impl.py` first (the docstrings on each `PriceRepo` method are the
contract). Import the thing under test from `src.sut`, not `src.impl` --
that indirection is how grading swaps in a mutant implementation:

    from src.sut import PriceRepo

Use the `conn` fixture from `tests/conftest.py` (a fresh psycopg connection
against a real, empty `observations` table for each test) -- do not open
your own connection or manage the container yourself.

Write real `def test_*(conn):` functions below. This file currently has
none, so `python -m pytest` collects 0 tests and fails -- that is expected
until you add some. See `hints/` if you get stuck, and
`../README.md` for the completion criteria.

Areas the grading mutant bank specifically probes -- your suite needs at
least one test that would fail if any of these broke:

  - Upsert idempotency: calling `upsert_observations` twice with the exact
    same rows must not create duplicate rows, and must leave the *latest*
    values (price/currency) in place, not the first ones.
  - Durability: after `upsert_observations` returns, the data must be
    visible to a *different* connection against the same database (not
    just readable back on the same connection before any commit).
  - Watermark boundary: `load_incremental(conn, since)` must return
    nothing for a row whose `scraped_at` is exactly equal to `since`, and
    must return every row strictly after it.
  - Pagination completeness: walking `page(conn, after, limit)` across
    multiple pages (by feeding each page's last row's cursor back in as
    the next `after`) must visit every row exactly once -- no row skipped
    and no row duplicated at a page boundary, including when several rows
    share the same `scraped_at` (the `id` tiebreak matters).
"""

from __future__ import annotations

from src.sut import PriceRepo  # noqa: F401

# TODO: write test_* functions here, each taking the `conn` fixture.
