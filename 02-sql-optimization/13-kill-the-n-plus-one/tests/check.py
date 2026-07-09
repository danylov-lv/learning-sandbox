"""Checker for 13-kill-the-n-plus-one.

Run from the module root:
    uv run python 13-kill-the-n-plus-one/tests/check.py
"""

import sys
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK_ROOT / "src"))

import psycopg  # noqa: E402
from psycopg import Cursor  # noqa: E402

from dashboard import fetch_dashboard  # noqa: E402

# Users chosen from a query against the live DB for the highest order
# counts among non-degenerate accounts (the single most-active synthetic
# user in this dataset has 2.6M orders -- not representative of a support
# case; these three have 60 orders each, a realistic "heavy user" case for
# a support agent to open).
USER_IDS = [712, 758, 827]
LIMIT = 30
MAX_QUERIES_PER_CALL = 4  # 3 for a set-based rewrite; 4 leaves room for
                          # splitting items/products into two queries


def conninfo():
    return "host=localhost port=54302 dbname=sandbox user=sandbox password=sandbox"


class _CountingCursor(Cursor):
    """Counts cur.execute() calls across the connection's lifetime."""
    calls = 0

    def execute(self, *args, **kwargs):
        _CountingCursor.calls += 1
        return super().execute(*args, **kwargs)


def count_queries(conn, user_id, limit):
    """Runs fetch_dashboard once, counting queries and wall time together
    (a second call would double naive stock's ~9s-per-user cost for no
    benefit)."""
    _CountingCursor.calls = 0
    prior_factory = conn.cursor_factory
    conn.cursor_factory = _CountingCursor
    try:
        t0 = time.perf_counter()
        result = fetch_dashboard(conn, user_id, limit)
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        conn.cursor_factory = prior_factory
        conn.rollback()
    return result, _CountingCursor.calls, elapsed_ms


def reference_dashboard(conn, user_id, limit):
    """Independent, set-based re-derivation of the same structure, used
    only to check result parity. Not a template for the learner's fix."""
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
        order_ids = [r[0] for r in order_rows]

        cur.execute(
            """
            SELECT oi.order_id, p.title, oi.quantity, oi.unit_price
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ANY(%(ids)s)
            ORDER BY oi.order_id, oi.id
            """,
            {"ids": order_ids},
        )
        items_by_order = {}
        for order_id, title, qty, unit_price in cur.fetchall():
            items_by_order.setdefault(order_id, []).append(
                {"product_title": title, "quantity": qty, "unit_price": str(unit_price)}
            )

        cur.execute(
            """
            SELECT DISTINCT ON (order_id) order_id, status, amount
            FROM payments
            WHERE order_id = ANY(%(ids)s)
            ORDER BY order_id, id DESC
            """,
            {"ids": order_ids},
        )
        payment_by_order = {
            order_id: {"status": status, "amount": str(amount)}
            for order_id, status, amount in cur.fetchall()
        }
    conn.rollback()

    return [
        {
            "order_id": order_id,
            "status": status,
            "total_amount": str(total_amount),
            "created_at": created_at.isoformat(),
            "items": items_by_order.get(order_id, []),
            "payment": payment_by_order.get(order_id),
        }
        for order_id, status, total_amount, created_at in order_rows
    ]


def main():
    conn = psycopg.connect(conninfo())

    over_limit = []
    parity_mismatches = []
    timings_current = []

    for user_id in USER_IDS:
        try:
            result, n_queries, elapsed_ms = count_queries(conn, user_id, LIMIT)
        except psycopg.Error as e:
            print(f"NOT PASSED: could not run fetch_dashboard for user {user_id}: {e}")
            sys.exit(1)

        timings_current.append(elapsed_ms)
        print(f"info  user {user_id}: {len(result)} orders, {n_queries} queries, {elapsed_ms:.1f}ms")
        if n_queries > MAX_QUERIES_PER_CALL:
            over_limit.append((user_id, n_queries))

        try:
            ref = reference_dashboard(conn, user_id, LIMIT)
        except psycopg.Error as e:
            print(f"NOT PASSED: could not compute reference for user {user_id}: {e}")
            sys.exit(1)

        if result != ref:
            parity_mismatches.append(user_id)

    if parity_mismatches:
        reason = (
            f"fetch_dashboard() output does not match the independently computed "
            f"reference for user(s) {parity_mismatches} -- check ordering of orders/"
            f"items and payment selection"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    print("PASS  fetch_dashboard() output matches the independent reference for all users")

    if over_limit:
        detail = ", ".join(f"user {u}: {n} queries" for u, n in over_limit)
        reason = (
            f"query count exceeds {MAX_QUERIES_PER_CALL} per call ({detail}) -- "
            "fetch_dashboard() is still issuing one query per order (N+1)"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    print(f"PASS  every call used <= {MAX_QUERIES_PER_CALL} queries, independent of order count")

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
