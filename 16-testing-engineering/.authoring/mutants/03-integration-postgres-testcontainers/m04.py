"""BUG: `page`'s keyset cursor uses `>=` instead of `>`.

The pagination WHERE clause is `(scraped_at, id) >= (%s, %s)` instead of
`>`. The row at the cursor -- the last row returned on the previous page --
is included again as the first row of the next page. Walking pages by
feeding each page's last row back in as `after` produces a duplicate at
every page boundary, and (since `limit` stays fixed) one real row gets
pushed off the end and never appears at all.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


class PriceRepo:
    """Data-access layer over the `observations` table."""

    @staticmethod
    def create_schema(conn) -> None:
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
                    WHERE (scraped_at, id) >= (%s, %s)
                    ORDER BY scraped_at, id
                    LIMIT %s
                    """,
                    (after_scraped_at, after_id, limit),
                )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
