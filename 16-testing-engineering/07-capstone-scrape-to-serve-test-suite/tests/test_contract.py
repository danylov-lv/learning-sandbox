"""YOUR DELIVERABLE (CP2) -- contract tests for the catalog API.

Read `src/impl.py` first -- `make_app`'s docstring is the contract, and
`PRODUCT_SCHEMA` / `CATALOG_PAGE_SCHEMA` / `ERROR_SCHEMA` are the JSON
Schemas the response bodies must satisfy. Import from `src.sut`:

    from src.sut import PRODUCT_SCHEMA, CATALOG_PAGE_SCHEMA, ERROR_SCHEMA

Use the `client` fixture from `tests/conftest.py` (a `fastapi.testclient.
TestClient` wrapping `make_app(repo, cache)` over real, fresh Postgres +
Redis containers) to drive the app over its actual HTTP surface -- do not
call route functions directly. Use `repo` (also available as a fixture)
to seed rows before asserting on what the API returns. Validate response
bodies against the schemas with `jsonschema.validate(...)`.

Write real `def test_*(client):` / `def test_*(client, repo):` functions
below. This file currently has none, so `python -m pytest` collects 0
tests and fails -- that is expected until you add some. This suite needs
Docker running (same containers as `test_integration.py`). See `hints/`
if you get stuck, and `../README.md` for the completion criteria.

Areas the CP2 mutant bank specifically probes -- your suite needs at
least one test that would fail if any of these broke:

  - Response shape: a `GET /products` page and a `GET /products/{sku}`
    item both validate against their JSON Schema (field names, types --
    e.g. `id` must be an `int`, not a `str`).
  - `next_cursor` presence: it is a real `int` when the page came back
    full (more rows may exist), and `null` when the page came back short
    (the last page) -- neither direction may be flipped.
  - 404 behavior: `GET /products/{sku}` for an unknown `sku` returns HTTP
    404 (not 200, not 400, not 500) with a body matching `ERROR_SCHEMA`.
  - Cache-read path: after a first `GET /products/{sku}` populates the
    cache, the API must keep returning the same product (you can prove
    the cache is actually being used, e.g. by checking `redis_client`
    directly, or by mutating the DB row underneath and confirming the
    cached response is still served).
"""

from __future__ import annotations

import jsonschema

from src.sut import CATALOG_PAGE_SCHEMA, ERROR_SCHEMA, PRODUCT_SCHEMA  # noqa: F401

# TODO: write test_* functions here, each taking the `client` fixture
# (and `repo` / `redis_client` as needed to seed or inspect state).
