"""MUTANT -- GET /products/{sku} for an unknown sku responds HTTP 400 instead of the documented HTTP 404.

A mini scrape-to-serve catalog stack, all four layers in this one file
(the mutation harness swaps a single file via `SUT_IMPL_PATH`, so the
whole stack has to live here to be mutable as one unit):

  - Parser layer (pure, no I/O): `parse_price` / `normalize_record` turn a
    raw scraped record into a canonical dict.
  - Repository layer: `CatalogRepo` over Postgres (`psycopg` v3) -- schema,
    idempotent upsert, keyset pagination, an incremental-load watermark
    query, and a single-row lookup by business key.
  - Cache layer: `ProductCache` over Redis (`redis-py`) -- a namespaced,
    TTL'd read-through cache for single-product lookups.
  - API layer: `make_app(repo, cache)` -- a FastAPI catalog API with
    cursor pagination and a structured error envelope on 404.

The learner reads this file to understand the contract, then writes three
test suites against it (unit/property, integration, contract). It is not
itself a spoiler: the task is "write tests that would catch a regression
here", not "reimplement this". Tests never import this module directly --
see `src/sut.py`.

Data model:

  A raw scraped record is a dict with keys `id` (the source site's product
  identifier -- becomes this stack's `sku`, a business key), `title`,
  `price` (a raw price string), `url`, and optionally `in_stock`.
  `normalize_record` turns that into a canonical dict keyed by `sku` (not
  `id` -- the DB layer has its own surrogate `id`, see below, and reusing
  the name would conflate two different identifiers).

  The Postgres `products` table has its own surrogate `id` (BIGSERIAL,
  insertion order, used only for keyset pagination) separate from `sku`
  (the business key from the source site, `UNIQUE`, used for idempotent
  upsert and single-product lookup). An API response item exposes both:
  `id` (int, the pagination cursor) and `sku` (str, the lookup key).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}

_PRICE_RE = re.compile(
    r"^(?P<sign>-)?\s*(?P<symbol>[$€£])?\s*(?P<number>[\d.,]+)\s*$"
)


class Price:
    """An immutable (amount, currency) value object.

    Not a `@dataclass` on purpose: this file is loaded standalone (via
    `importlib.util.spec_from_file_location`, see `src/sut.py`) rather
    than as a normal package import, and is never registered in
    `sys.modules` under that loading path -- `dataclasses`' own
    annotation-resolution machinery needs `sys.modules[cls.__module__]`
    and raises `AttributeError` on `None` without it. A plain class with
    explicit `__init__`/`__eq__`/`__repr__` sidesteps that entirely.
    """

    def __init__(self, amount: Decimal, currency: str) -> None:
        self.amount = amount
        self.currency = currency

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.amount == other.amount and self.currency == other.currency

    def __hash__(self) -> int:
        return hash((self.amount, self.currency))

    def __repr__(self) -> str:
        return f"Price(amount={self.amount!r}, currency={self.currency!r})"


def parse_price(raw: str) -> Price:
    """Parse a raw scraped price string into a `Price`.

    Accepts an optional leading `-` sign, an optional currency symbol
    (`$`, `€`, `£` -> USD/EUR/GBP respectively, default USD when no
    symbol is present), and a numeric part that uses `,` as a thousands
    separator and `.` as the decimal separator (e.g. "$1,234.56" ->
    amount 1234.56). Raises `ValueError` -- never returns `None` -- on
    anything that does not match this grammar, including an empty string,
    a string with no digits, or a number with more than one decimal
    point.
    """
    if raw is None:
        raise ValueError("price string is None")
    text = raw.strip()
    match = _PRICE_RE.match(text)
    if not match:
        raise ValueError(f"unparseable price: {raw!r}")
    number = match.group("number")
    cleaned = number.replace(",", "")
    if cleaned.count(".") > 1 or cleaned in ("", "."):
        raise ValueError(f"unparseable price: {raw!r}")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"unparseable price: {raw!r}") from exc
    if match.group("sign"):
        amount = -amount
    symbol = match.group("symbol")
    currency = CURRENCY_SYMBOLS.get(symbol, "USD") if symbol else "USD"
    return Price(amount=amount, currency=currency)


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one raw scraped product record into canonical form.

    `raw` must have keys `id`, `title`, `price` (a raw price string parsed
    via `parse_price`), and `url`. `in_stock` is optional and defaults to
    `True` if absent, coerced to `bool` otherwise.

    Returns a dict with keys `sku` (str, from `raw["id"]`), `title` (str,
    surrounding whitespace stripped and internal runs of whitespace
    collapsed to a single space), `price_amount` (str form of the parsed
    `Decimal`, e.g. `"19.99"`), `currency` (str), `url` (str, stripped),
    `in_stock` (bool).

    Raises `KeyError` naming the missing key if `id`, `title`, `price`, or
    `url` is absent, and lets `parse_price`'s `ValueError` propagate
    unchanged for a malformed price.
    """
    for key in ("id", "title", "price", "url"):
        if key not in raw:
            raise KeyError(key)
    price = parse_price(raw["price"])
    title = " ".join(str(raw["title"]).split())
    return {
        "sku": str(raw["id"]),
        "title": title,
        "price_amount": str(price.amount),
        "currency": price.currency,
        "url": str(raw["url"]).strip(),
        "in_stock": bool(raw.get("in_stock", True)),
    }


class CatalogRepo:
    """Data-access layer over the `products` table.

    Every method uses the `psycopg` (v3) connection passed to `__init__`.
    This class does not own connection lifecycle (open/close) -- that is
    the caller's job (see `tests/conftest.py`'s fixtures for this task).
    """

    def __init__(self, conn) -> None:
        self._conn = conn

    def create_schema(self) -> None:
        """Create the `products` table if it does not already exist.

        `id` is a surrogate primary key (insertion order, used only for
        keyset pagination). `sku` is the business key from the source
        site, `UNIQUE`, which is what makes `upsert_products` idempotent
        via `ON CONFLICT (sku)` and what `get_by_sku` looks up by.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id BIGSERIAL PRIMARY KEY,
                    sku TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    price_amount NUMERIC NOT NULL,
                    currency TEXT NOT NULL,
                    url TEXT NOT NULL,
                    in_stock BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        self._conn.commit()

    def upsert_products(self, records: list[dict[str, Any]]) -> None:
        """Idempotently insert products, updating on conflict.

        Each record is a dict shaped like `normalize_record`'s output
        (`sku`, `title`, `price_amount`, `currency`, `url`, `in_stock`).
        Re-running with the same `sku` values must not create duplicate
        rows -- it updates every other column and bumps `updated_at` to
        `now()` in place. Commits so the write is durable for any
        connection that reads afterward, including a fresh one.
        """
        if not records:
            return
        with self._conn.cursor() as cur:
            for r in records:
                cur.execute(
                    """
                    INSERT INTO products (sku, title, price_amount, currency, url, in_stock, updated_at)
                    VALUES (%(sku)s, %(title)s, %(price_amount)s, %(currency)s, %(url)s, %(in_stock)s, now())
                    ON CONFLICT (sku)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        price_amount = EXCLUDED.price_amount,
                        currency = EXCLUDED.currency,
                        url = EXCLUDED.url,
                        in_stock = EXCLUDED.in_stock,
                        updated_at = now()
                    """,
                    {
                        "sku": r["sku"],
                        "title": r["title"],
                        "price_amount": Decimal(str(r["price_amount"])),
                        "currency": r["currency"],
                        "url": r["url"],
                        "in_stock": bool(r["in_stock"]),
                    },
                )
        self._conn.commit()

    def page(self, after: int | None, limit: int) -> list[dict[str, Any]]:
        """Keyset-paginate products ordered by surrogate `id`.

        `after` is `None` for the first page, or the `id` of the last row
        seen on the previous page for any subsequent page. Returns up to
        `limit` rows with `id` strictly greater than `after`, ascending.
        A caller that walks pages by repeatedly passing the last row's
        `id` back in must see every row exactly once, with no gaps or
        repeats at page boundaries.
        """
        with self._conn.cursor() as cur:
            if after is None:
                cur.execute(
                    """
                    SELECT id, sku, title, price_amount, currency, url, in_stock
                    FROM products
                    ORDER BY id
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, sku, title, price_amount, currency, url, in_stock
                    FROM products
                    WHERE id > %s
                    ORDER BY id
                    LIMIT %s
                    """,
                    (after, limit),
                )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def load_incremental(self, since: datetime) -> list[dict[str, Any]]:
        """Return products with `updated_at` strictly after `since`.

        `since` is a watermark: a caller that last processed up to and
        including some timestamp passes that timestamp back in and must
        never see that exact row again, only rows strictly newer. Ordered
        by `(updated_at, id)` ascending.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sku, title, price_amount, currency, url, in_stock, updated_at
                FROM products
                WHERE updated_at > %s
                ORDER BY updated_at, id
                """,
                (since,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_by_sku(self, sku: str) -> dict[str, Any] | None:
        """Look up a single product by its business key. `None` if absent."""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, sku, title, price_amount, currency, url, in_stock
                FROM products
                WHERE sku = %s
                """,
                (sku,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d.name for d in cur.description]
            return dict(zip(cols, row))


class ProductCache:
    """A namespaced, TTL'd read-through cache for single-product lookups
    over Redis (`redis-py`). Values are stored JSON-encoded.
    """

    NAMESPACE = "catalog:product:"

    def __init__(self, client, default_ttl: int = 60) -> None:
        self._client = client
        self._default_ttl = default_ttl

    def _key(self, sku: str) -> str:
        return f"{self.NAMESPACE}{sku}"

    def get(self, sku: str) -> dict[str, Any] | None:
        """Return the cached product for `sku`, or `None` on a cache miss."""
        raw = self._client.get(self._key(sku))
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, sku: str, product: dict[str, Any], ttl: int | None = None) -> None:
        """Cache `product` under `sku` with an expiry (`ttl` seconds, or
        `default_ttl` from `__init__` if `ttl` is not given). The key
        must always carry an expiry -- a cache entry that never expires
        would serve stale data forever after a product changes.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl
        self._client.set(self._key(sku), json.dumps(product), ex=effective_ttl)

    def invalidate(self, sku: str) -> None:
        """Remove any cached entry for `sku`."""
        self._client.delete(self._key(sku))


PRODUCT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "sku", "title", "price_amount", "currency", "url", "in_stock"],
    "properties": {
        "id": {"type": "integer"},
        "sku": {"type": "string"},
        "title": {"type": "string"},
        "price_amount": {"type": "string"},
        "currency": {"type": "string"},
        "url": {"type": "string"},
        "in_stock": {"type": "boolean"},
    },
    "additionalProperties": False,
}

CATALOG_PAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["items", "next_cursor"],
    "properties": {
        "items": {"type": "array", "items": PRODUCT_SCHEMA},
        "next_cursor": {"type": ["integer", "null"]},
    },
    "additionalProperties": False,
}

ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message"],
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
            },
        }
    },
    "additionalProperties": False,
}


def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sku": row["sku"],
        "title": row["title"],
        "price_amount": str(row["price_amount"]),
        "currency": row["currency"],
        "url": row["url"],
        "in_stock": row["in_stock"],
    }


def make_app(repo: CatalogRepo, cache: ProductCache) -> FastAPI:
    """Build the catalog FastAPI app over an already-constructed `repo`
    and `cache` (dependency injection at app-build time, not per-request
    -- this task's tests build one `repo`/`cache` pair per test and pass
    them in directly).

    Routes:

      `GET /products?cursor=&limit=` -- a page of products ordered by
      surrogate `id`. `cursor` (optional int) is the `id` of the last row
      seen on the previous page; `limit` (default 20, 1..100) caps the
      page size. Response body matches `CATALOG_PAGE_SCHEMA`:
      `{"items": [...], "next_cursor": <int> | null}`. `next_cursor` is
      the last item's `id` when the page came back full (`len(items) ==
      limit`, meaning there may be more), and `null` when the page came
      back short (the last page -- there is nothing more to fetch).

      `GET /products/{sku}` -- a single product by its business key.
      Tries the cache first; on a cache miss, reads from `repo`, writes
      the result back into the cache, then returns it. Response body
      matches `PRODUCT_SCHEMA` on success (HTTP 200). If no product has
      that `sku`, responds HTTP 404 with a body matching `ERROR_SCHEMA`:
      `{"error": {"code": "not_found", "message": "..."}}`.
    """
    app = FastAPI(title="catalog API")

    @app.get("/products")
    def list_products(
        cursor: int | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ):
        rows = repo.page(cursor, limit)
        items = [_row_to_item(r) for r in rows]
        next_cursor = items[-1]["id"] if len(items) == limit else None
        return {"items": items, "next_cursor": next_cursor}

    @app.get("/products/{sku}")
    def get_product(sku: str):
        cached = cache.get(sku)
        if cached is not None:
            return cached
        row = repo.get_by_sku(sku)
        if row is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "not_found",
                        "message": f"no product with sku {sku!r}",
                    }
                },
            )
        item = _row_to_item(row)
        cache.set(sku, item)
        return item

    return app
