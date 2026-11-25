"""BUG: `page`'s keyset cursor drops the `id` tiebreak from its WHERE clause.

The cursor predicate is `scraped_at > %s` (comparing only the timestamp)
instead of the full tuple `(scraped_at, id) > (%s, %s)`, even though
`ORDER BY scraped_at, id` and the result set still expose `id`. When two
or more rows share the exact same `scraped_at`, only the FIRST of them
(by id) is ever returned -- any sibling row with the same `scraped_at` as
the cursor row is permanently skipped, because `scraped_at > %s` excludes
anything whose timestamp merely equals the cursor's, regardless of its
`id`. Pagination silently loses rows whenever two observations land in the
same instant.
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
                    WHERE scraped_at > %s
                    ORDER BY scraped_at, id
                    LIMIT %s
                    """,
                    (after_scraped_at, limit),
                )
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
