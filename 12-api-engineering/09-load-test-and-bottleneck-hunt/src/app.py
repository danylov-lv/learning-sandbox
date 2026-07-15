"""s12.t09 -- catalog browse endpoint over shop.products/shop.sellers.

STOCK CODE IS DELIBERATELY WORKING -- your job is to fix it in place; do not
delete or reshape its observable behavior, make it fast. This is the same
spirit as task 06 (SQL injection): a real, running FastAPI app, not a
`NotImplementedError` stub. Every response it returns today is correct.
Whatever is wrong with it does not show up by reading a single response --
it shows up under concurrent load. See README.md for the full contract and
hints/ for how to go about finding it.

The story: `GET /catalog/{category_id}?limit=&offset=` is a category-browse
endpoint for the marketplace -- "show me a page of products in this
category, with each product's seller name and tier attached" (a normal
product-listing widget: nobody wants to see a bare seller_id). It reads
ONLY the shared, read-only `shop.products` / `shop.sellers` tables.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from fastapi import FastAPI, Query  # noqa: E402

from harness.common import pg_pool  # noqa: E402

LIMIT_MIN, LIMIT_MAX, LIMIT_DEFAULT = 1, 100, 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = pg_pool(min_size=1, max_size=1)
    app.state.pool = pool
    yield
    pool.close()


app = FastAPI(title="s12.t09 catalog browse", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/catalog/{category_id}")
async def catalog(category_id: int, limit: int = Query(LIMIT_DEFAULT), offset: int = Query(0)):
    """Page shop.products in `category_id`, each item enriched with its
    seller's name/tier. Returns:
        {"category_id", "limit", "offset",
         "items": [{"id", "title", "price", "seller_name", "seller_tier"}, ...]}
    ordered by product id ascending.
    """
    limit = max(LIMIT_MIN, min(limit, LIMIT_MAX))
    offset = max(0, offset)
    pool = app.state.pool

    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, title, price, seller_id FROM shop.products "
            "WHERE category_id = %s ORDER BY id LIMIT %s OFFSET %s",
            (category_id, limit, offset),
        ).fetchall()

    items = []
    for product_id, title, price, seller_id in rows:
        with pool.connection() as seller_conn:
            seller = seller_conn.execute(
                "SELECT name, tier FROM shop.sellers WHERE id = %s", (seller_id,)
            ).fetchone()
        items.append(
            {
                "id": product_id,
                "title": title,
                "price": float(price),
                "seller_name": seller[0] if seller else None,
                "seller_tier": seller[1] if seller else None,
            }
        )

    return {"category_id": category_id, "limit": limit, "offset": offset, "items": items}
