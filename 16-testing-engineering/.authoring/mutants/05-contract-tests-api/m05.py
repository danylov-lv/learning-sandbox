"""BUG: `id` is serialized as a JSON string (e.g. "7") instead of a JSON
integer on the `/products` collection endpoint -- a consumer doing
`isinstance(item["id"], int)` or arithmetic on the id silently breaks.
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

        page_out = [{**p, "id": str(p["id"])} for p in page]

        return JSONResponse(
            content={"items": page_out, "next_cursor": next_cursor},
            headers={"Cache-Control": "public, max-age=30"},
        )

    @app.get("/products/{product_id}")
    async def get_product(product_id: int) -> dict:
        product = _PRODUCTS_BY_ID.get(product_id)
        if product is None:
            raise NotFoundError(f"product {product_id} not found")
        return product

    return app
