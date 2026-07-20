"""Catalog API -- the CORRECT, given implementation for this task.

You are the consumer team. Some other team owns this service and hands you
`make_app()` plus the response contract described in `src/contract.json`.
Your job in this task is NOT to change anything here -- it is to write a
test suite (`tests/test_contract.py`) that would fail loudly the moment a
future refactor of this service silently breaks the contract your code
depends on. Read this file to understand the contract; do not edit it.

Endpoints
---------

GET /products?cursor=&limit=
    Cursor pagination over a fixed, in-memory product catalog, ordered by
    `id` ascending. `cursor` is the string form of the last `id` seen on
    the previous page (omit it for the first page). `limit` defaults to 10
    and is clamped to [1, 100].

    200 -> {"items": [product, ...], "next_cursor": <str> | null}

    `next_cursor` is a STRING when another page remains, and exactly
    `null` (never omitted, never an empty string) once the page returned
    is the last one. Walking cursor -> next_cursor -> ... from `None`
    visits every product in the catalog exactly once, in id order, and
    terminates in a finite number of pages.

    Also sets a `Cache-Control: public, max-age=30` response header on
    this endpoint -- the collection is safe for a consumer to cache
    briefly.

GET /products/{id}
    200 -> the product object with that id.
    404 -> {"error": {"code": "not_found", "message": <str>}} if no
    product has that id. This is the ONLY error shape this service ever
    returns -- there is no bare `{"detail": ...}` anywhere.

Product object shape (see `src/contract.json` for the JSON Schema):
    {"id": int, "name": str, "price": str, "currency": str}

    `id` is a JSON integer, never a numeric string. `price` is a decimal
    STRING with exactly two fraction digits (e.g. "18.50"), never a JSON
    number -- floats lose exact cents, strings don't. `currency` is a
    3-letter ISO code string.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

DEFAULT_LIMIT = 10
MAX_LIMIT = 100

_CATALOG_NAMES = [
    "Aluminum Water Bottle",
    "Canvas Tote Bag",
    "Ceramic Coffee Mug",
    "Wireless Mouse",
    "Mechanical Keyboard",
    "Desk Lamp",
    "Notebook, Ruled",
    "Fountain Pen",
    "Wool Beanie",
    "Leather Wallet",
    "Bluetooth Speaker",
    "Travel Pillow",
    "Stainless Steel Thermos",
    "Bamboo Cutting Board",
    "Cast Iron Skillet",
    "Yoga Mat",
    "Resistance Bands",
    "Running Socks (3-pack)",
    "Rain Jacket",
    "Hiking Backpack",
    "Solar Power Bank",
    "USB-C Cable, 2m",
    "Phone Tripod",
]

_PRODUCTS = [
    {
        "id": i + 1,
        "name": name,
        "price": f"{9.99 + i * 2.5:.2f}",
        "currency": "USD",
    }
    for i, name in enumerate(_CATALOG_NAMES)
]
_PRODUCTS_BY_ID = {p["id"]: p for p in _PRODUCTS}


class NotFoundError(Exception):
    """Raised when a product id has no match. Carries the human-readable message."""

    def __init__(self, message: str) -> None:
        self.message = message


def make_app() -> FastAPI:
    app = FastAPI(title="Catalog API")

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "not_found", "message": exc.message}},
        )

    @app.get("/products")
    async def list_products(
        cursor: str | None = Query(default=None),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    ) -> JSONResponse:
        if cursor is None:
            after_id = 0
        else:
            try:
                after_id = int(cursor)
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid cursor")

        remaining = [p for p in _PRODUCTS if p["id"] > after_id]
        page = remaining[:limit]
        has_more = len(remaining) > len(page)
        next_cursor = str(page[-1]["id"]) if (page and has_more) else None

        return JSONResponse(
            content={"items": page, "next_cursor": next_cursor},
            headers={"Cache-Control": "public, max-age=30"},
        )

    @app.get("/products/{product_id}")
    async def get_product(product_id: int) -> dict:
        product = _PRODUCTS_BY_ID.get(product_id)
        if product is None:
            raise NotFoundError(f"product {product_id} not found")
        return product

    return app
