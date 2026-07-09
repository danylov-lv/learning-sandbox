"""Support dashboard data access -- STOCK naive implementation.

This is the starting defect, not a solution: fetch_dashboard() below
issues one query for the user's orders, then two more queries PER ORDER
(one for line items + product titles, one for the payment). For a user
with dozens of orders that's 1 + 2*N round trips.

Rewrite the body of fetch_dashboard() (same signature, same returned
structure -- see README) so it uses a constant number of queries
regardless of how many orders the user has.
"""


def fetch_dashboard(conn, user_id, limit=30):
    """Return a support-dashboard view for one user.

    Returned structure:
        [
            {
                "order_id": int,
                "status": str,
                "total_amount": str,          # decimal as string
                "created_at": str,             # ISO 8601
                "items": [
                    {"product_title": str, "quantity": int, "unit_price": str},
                    ...                         # ordered by order_items.id ascending
                ],
                "payment": {"status": str, "amount": str} or None,
            },
            ...                                  # orders ordered newest-first (created_at
                                                  # DESC, then id DESC as a tiebreaker),
                                                  # at most `limit` orders
        ]
    """
    orders = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, status, total_amount, created_at
            FROM orders
            WHERE user_id = %(user_id)s
            ORDER BY created_at DESC, id DESC
            LIMIT %(limit)s
            """,
            {"user_id": user_id, "limit": limit},
        )
        order_rows = cur.fetchall()

    for order_id, status, total_amount, created_at in order_rows:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.title, oi.quantity, oi.unit_price
                FROM order_items oi
                JOIN products p ON p.id = oi.product_id
                WHERE oi.order_id = %(order_id)s
                ORDER BY oi.id ASC
                """,
                {"order_id": order_id},
            )
            items = [
                {"product_title": title, "quantity": qty, "unit_price": str(unit_price)}
                for title, qty, unit_price in cur.fetchall()
            ]

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, amount
                FROM payments
                WHERE order_id = %(order_id)s
                ORDER BY id DESC
                LIMIT 1
                """,
                {"order_id": order_id},
            )
            row = cur.fetchone()
            payment = {"status": row[0], "amount": str(row[1])} if row is not None else None

        orders.append(
            {
                "order_id": order_id,
                "status": status,
                "total_amount": str(total_amount),
                "created_at": created_at.isoformat(),
                "items": items,
                "payment": payment,
            }
        )

    return orders
