"""s12.t01 -- offset vs. cursor (keyset) pagination over shop.products.

You are building the catalog-listing endpoints of a marketplace API. Both
page through the SHARED, READ-ONLY `shop.products` corpus (200,000 rows;
ids are a contiguous 1..200000 range), ordered by `id` ascending. Never
write to `shop`.

Two endpoints to implement:

  GET /products/offset?limit=<int>&offset=<int>
      Classic LIMIT/OFFSET pagination. Returns
          {"items": [...], "limit": <int>, "offset": <int>}
      Each item is at least {"id": int, "title": str, "price": float}.
      The SQL is `... ORDER BY id LIMIT :limit OFFSET :offset`.

  GET /products/cursor?limit=<int>&cursor=<int-or-omitted>
      Keyset ("seek method") pagination. Returns
          {"items": [...], "next_cursor": <id or null>}
      `cursor` is the last id seen on the previous page (omit it, or pass
      nothing, for the first page). The SQL is a KEYSET filter, NOT an
      offset:
          `... WHERE id > :cursor ORDER BY id LIMIT :limit`
      `next_cursor` is the id of the LAST item returned, or null once the
      page came back short / empty (the catalog is exhausted). Document your
      token choice: the simplest opaque token here is just the last id, and
      that is what the validator assumes.

Both endpoints must survive bad params (a negative or absurdly large limit
should be clamped to a sane range; a negative/garbage offset or cursor
handled gracefully) -- but that is secondary to getting the two pagination
strategies correct.

Connecting to Postgres: the module harness gives you ready-made helpers --
`from harness.common import pg_pool, pg_conn, pg_dsn`. A FastAPI lifespan
that opens one `pg_pool()` and reuses a pooled connection per request is the
idiomatic shape; opening a fresh `pg_conn()` per request also works and is
simpler to start with. (Both `harness` and this `src` package are importable
because the validator and baseline scripts put the task root and module root
on `sys.path`.)

The two route bodies below `raise NotImplementedError`, so the app imports
and launches fine -- every route just answers HTTP 501 until you implement
it (a registered handler turns the NotImplementedError into a clean 501, so
there is no traceback). Replace each body with your implementation.
"""

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="s12.t01 offset vs cursor pagination")


@app.exception_handler(NotImplementedError)
async def _not_implemented(request, exc):
    return JSONResponse(
        status_code=501,
        content={"detail": "endpoint not implemented yet -- implement it in src/app.py"},
    )


@app.get("/products/offset")
async def products_offset(limit: int = Query(20), offset: int = Query(0)):
    """OFFSET pagination over shop.products ordered by id.

    Return {"items": [{"id", "title", "price"}, ...], "limit", "offset"}.
    """
    raise NotImplementedError


@app.get("/products/cursor")
async def products_cursor(limit: int = Query(20), cursor: int | None = Query(default=None)):
    """KEYSET (cursor) pagination over shop.products ordered by id ASC.

    Use `WHERE id > :cursor ORDER BY id LIMIT :limit` -- NOT an offset.
    Return {"items": [{"id", "title", "price"}, ...], "next_cursor": <id|null>}.
    """
    raise NotImplementedError
