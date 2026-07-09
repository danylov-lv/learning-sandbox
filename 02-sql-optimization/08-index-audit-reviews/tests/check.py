"""Checker for 08-index-audit-reviews.

Run from the module root:
    uv run python 08-index-audit-reviews/tests/check.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import PlanAssertionError, conninfo, forbid_node, get_plan, require_node  # noqa: E402
import baseline  # noqa: E402

DROPPED_INDEXES = ["idx_reviews_product_id", "idx_reviews_review_text"]


def existing_indexes(cur):
    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'reviews'")
    return {row[0] for row in cur.fetchall()}


def sample_product_id(cur):
    # the product with the most reviews -- the least favorable case for an
    # index scan, since it's the least selective product_id in the table.
    cur.execute(
        "SELECT product_id FROM reviews GROUP BY product_id ORDER BY count(*) DESC LIMIT 1"
    )
    return cur.fetchone()[0]


def main():
    try:
        with psycopg.connect(conninfo()) as conn:
            with conn.cursor() as cur:
                present = existing_indexes(cur)
                pid = sample_product_id(cur)
                cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
                uid = cur.fetchone()[0]
            conn.rollback()
    except psycopg.Error as e:
        print(f"NOT PASSED: could not inspect the database: {e}")
        sys.exit(1)

    still_present = [ix for ix in DROPPED_INDEXES if ix in present]
    if still_present:
        reason = (
            f"still present, not yet dropped: {', '.join(still_present)} "
            "(check src/workload.md -- neither is needed by any documented read pattern)"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)
    print(f"PASS  redundant indexes gone ({', '.join(DROPPED_INDEXES)})")

    workload = [
        (
            "recent reviews for a product",
            f"SELECT id, user_id, rating, review_text, created_at FROM reviews "
            f"WHERE product_id = {pid} ORDER BY created_at DESC LIMIT 10",
        ),
        (
            "rating summary for a product",
            f"SELECT rating, count(*) FROM reviews WHERE product_id = {pid} GROUP BY rating",
        ),
        (
            "review count for a product",
            f"SELECT count(*) FROM reviews WHERE product_id = {pid}",
        ),
    ]

    for name, sql in workload:
        try:
            plan = get_plan(sql)
            forbid_node(plan, "Seq Scan", table="reviews")
            require_node(plan, "Index Scan", table="reviews")
        except PlanAssertionError as e:
            reason = f"workload query '{name}' broke: {e}"
            print(f"FAIL  {reason}")
            print(f"NOT PASSED: {reason}")
            sys.exit(1)
        except psycopg.Error as e:
            print(f"NOT PASSED: could not run workload query '{name}': {e}")
            sys.exit(1)
        print(f"PASS  workload query '{name}' still index-driven")

    # Informational only: no threshold, just show the write-amplification win.
    insert_sql = (
        f"INSERT INTO reviews (product_id, user_id, rating, review_text, created_at) "
        f"VALUES ({pid}, {uid}, 4, 'audit check sample review text', now())"
    )
    try:
        timings = baseline.time_query(insert_sql, runs=20, warmups=2)
        print(f"info  single-row INSERT into reviews, current indexes: median {statistics.median(timings):.3f} ms")
    except psycopg.Error as e:
        print(f"info  could not time a sample INSERT: {e}")

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
