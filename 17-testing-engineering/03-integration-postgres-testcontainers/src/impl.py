"""Correct implementation -- GIVEN, do not edit.

`PriceRepo` is a data-access layer over a Postgres `observations` table for
a price-scraping pipeline: one row per (product_url, scraped_at) price
observation. Every method takes an open `psycopg` (v3) connection as its
first argument; none of them own connection lifecycle -- that is the
caller's job (see `tests/conftest.py`'s fixtures for this task).

The learner reads this file to understand the contract, then writes
`tests/test_repo.py` against it. It is not itself a spoiler: the task is
"write an integration test suite that would catch a regression here", not
"reimplement this".
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class PriceRepo:
    """Data-access layer over the `observations` table."""

    @staticmethod
    def create_schema(conn) -> None:
        """Create the `observations` table if it does not already exist.

        Columns: `id` (surrogate PK), `product_url` (text), `scraped_at`
        (timestamptz), `price` (numeric), `currency` (text). A unique
        constraint on `(product_url, scraped_at)` is what makes
        `upsert_observations` idempotent via `ON CONFLICT`.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    id BIGSERIAL PRIMARY KEY,
                    product_url TEXT NOT NULL,
                    scraped_at TIMESTAMPTZ NOT NULL,
                    price NUMERIC NOT NULL,
                    currency TEXT NOT NULL,
                    UNIQUE (product_url, scraped_at)
                )
                """
            )
        conn.commit()

    @staticmethod
    def upsert_observations(conn, rows: list[dict[str, Any]]) -> None:
        """Idempotently insert observations, updating on conflict.

        Each row is a dict with keys `product_url`, `scraped_at`, `price`,
        `currency`. Re-running with the same `(product_url, scraped_at)`
        pairs must not create duplicate rows -- it updates `price` and
        `currency` in place. Commits so the write is durable for any
        connection that reads afterward, including a fresh one.
        """
        if not rows:
            return
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO observations (product_url, scraped_at, price, currency)
                    VALUES (%(product_url)s, %(scraped_at)s, %(price)s, %(currency)s)
                    ON CONFLICT (product_url, scraped_at)
                    DO UPDATE SET price = EXCLUDED.price, currency = EXCLUDED.currency
                    """,
                    row,
                )
        conn.commit()

    @staticmethod
    def load_incremental(conn, since: datetime) -> list[dict[str, Any]]:
        """Return observations with `scraped_at` strictly after `since`.

        `since` is a watermark: a caller that last processed up to and
        including some timestamp passes that timestamp back in and must
        never see that exact row again, only rows strictly newer. Ordered
        by `(scraped_at, id)` ascending.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, product_url, scraped_at, price, currency
                FROM observations
                WHERE scraped_at > %s
                ORDER BY scraped_at, id
                """,
                (since,),
            )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    @staticmethod
    def page(conn, after: tuple[Any, int] | None, limit: int) -> list[dict[str, Any]]:
        """Keyset-paginate observations ordered by `(scraped_at, id)`.

        `after` is `None` for the first page, or the `(scraped_at, id)`
        cursor of the last row seen on the previous page for any
        subsequent page. Returns up to `limit` rows strictly after that
        cursor in `(scraped_at, id)` order -- the `id` tiebreak matters
        because multiple rows can share the same `scraped_at`. A caller
        that walks pages by repeatedly passing the last row's cursor back
        in must see every row exactly once, with no gaps or repeats at
        page boundaries.
        """
        with conn.cursor() as cur:
            if after is None:
                cur.execute(
                    """
                    SELECT id, product_url, scraped_at, price, currency
                    FROM observations
                    ORDER BY scraped_at, id
                    LIMIT %s
                    """,
                    (limit,),
                )
            else:
                after_scraped_at, after_id = after
                cur.execute(
                    """
                    SELECT id, product_url, scraped_at, price, currency
                    FROM observations
                    WHERE (scraped_at, id) > (%s, %s)
                    ORDER BY scraped_at, id
                    LIMIT %s
                    """,
                    (after_scraped_at, after_id, limit),
                )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
