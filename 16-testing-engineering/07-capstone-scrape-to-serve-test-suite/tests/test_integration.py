"""YOUR DELIVERABLE (CP2) -- integration tests for `CatalogRepo` and
`ProductCache` against real Postgres and Redis containers.

Read `src/impl.py` first. Import from `src.sut`:

    from src.sut import CatalogRepo, ProductCache

Use the `repo` / `cache` fixtures from `tests/conftest.py` (a `CatalogRepo`
over a fresh, empty `products` table, and a `ProductCache` over a fresh,
flushed Redis) -- do not open your own connections or manage containers
yourself. The `redis_client` fixture is also available directly if you
need to inspect raw Redis state (e.g. `TTL`) that `ProductCache`'s own
methods do not expose.

Write real `def test_*(repo):` / `def test_*(cache):` /
`def test_*(repo, cache):` functions below. This file currently has none,
so `python -m pytest` collects 0 tests and fails -- that is expected
until you add some. This suite needs Docker running (it starts real
Postgres + Redis containers the first time a session-scoped fixture is
used). See `hints/` if you get stuck, and `../README.md` for the
completion criteria.

Areas the CP2 mutant bank specifically probes -- your suite needs at
least one test that would fail if any of these broke:

  Repository (`CatalogRepo`):
  - Upsert idempotency: calling `upsert_products` twice with the same
    `sku` must not create duplicate rows, and must leave the *latest*
    values in place, not the first ones.
  - Durability: after `upsert_products` returns, the data must be visible
    to a *different* connection against the same database.
  - Watermark boundary: `load_incremental(since)` must return nothing for
    a row whose `updated_at` equals `since` exactly, and must return
    every row strictly after it.
  - Pagination completeness: walking `page(after, limit)` across multiple
    pages (feeding each page's last row's `id` back in) must visit every
    row exactly once -- no row skipped, none duplicated.
  - `get_by_sku` for an absent `sku` returns `None`, not an exception or
    a stale row.

  Cache (`ProductCache`):
  - `set` followed by `get` for the same `sku` returns the value back.
  - Every cached key carries a real TTL (check with `redis_client.ttl(...)`)
    -- it must never be set to "no expiry".
  - Two different `sku`s must not collide in Redis (correct namespacing).
  - `get` for a `sku` that was never `set` (or was `invalidate`d) returns
    `None`.
"""

from __future__ import annotations

from src.sut import CatalogRepo, ProductCache  # noqa: F401

# TODO: write test_* functions here, each taking the `repo` and/or
# `cache` (and/or `redis_client`) fixtures.
