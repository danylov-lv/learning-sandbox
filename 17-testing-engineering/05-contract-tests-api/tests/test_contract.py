"""Consumer contract tests for the catalog API -- YOUR deliverable.

The service under test is `src.sut.make_app()` (a FastAPI app). Import it
from `src.sut`, never from `src.impl` directly -- see the module docstring
in `src/impl.py` for why.

The contract you are testing lives in two places:
  - `src/impl.py`'s module docstring (the prose contract).
  - `src/contract.json` (the JSON Schema for `product`, `product_list`,
    and `error` -- load it with `json.load` and validate response bodies
    against it with `jsonschema.validate`).

Drive the app in-process with `fastapi.testclient.TestClient(make_app())`
-- no server, no container. (`httpx.ASGITransport` also works, but it is
async-only: pair it with `httpx.AsyncClient`, not the sync `httpx.Client`.)

TODO -- write tests that assert, at minimum:
  1. Schema conformance: every product in a `/products` page, and the
     product returned by `/products/{id}`, matches `contract.json`'s
     `product` schema. The full `/products` response matches
     `product_list`. A 404 body matches `error`.
  2. Pagination invariants:
       - walking `cursor -> next_cursor -> ...` from the first page visits
         every product in the catalog EXACTLY once (no gaps, no repeats),
         and terminates;
       - `next_cursor` is `null` on the last page;
       - `next_cursor` is a non-null string on every page that is NOT the
         last page (mid-stream).
  3. The error contract: `GET /products/{id}` for an id that does not
     exist returns exactly `404` with the `error` envelope shape -- not
     `200` with something null-ish, not `500`, not a bare `{"detail": ...}`.
  4. Type stability: `id` deserializes as a JSON int (`isinstance(x, int)`
     and NOT `isinstance(x, bool)` -- careful, Python's `bool` is an `int`
     subclass), `price` deserializes as a `str`, not a `float`.

A suite that only checks `status_code == 200` on the happy path will not
catch a shape/status/pagination/type regression -- inspect the body.

Nothing below is a real test yet -- that's the point of a scaffold. Delete
this placeholder once you've written real tests.
"""

from __future__ import annotations

# TODO: import fastapi.testclient.TestClient (or httpx.AsyncClient +
# ASGITransport), jsonschema, json, pathlib -- and `from src.sut import
# make_app`.
