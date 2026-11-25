"""BUG: `price` is serialized as a JSON number (float) instead of a
decimal string -- a consumer that treats price as opaque text (to avoid
float rounding on money) gets a `float` and can lose exact cents.
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
        "price": float(f"{9.99 + i * 2.5:.2f}"),
        "currency": "USD",
    }
    for i, name in enumerate(_CATALOG_NAMES)
]
_PRODUCTS_BY_ID = {p["id"]: p for p in _PRODUCTS}


class NotFoundError(Exception):
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
