"""Checker for 03-order-detail-join.

Run from the module root:
    uv run python 03-order-detail-join/tests/check.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import PlanAssertionError, conninfo, forbid_node, get_plan, require_node  # noqa: E402
import baseline  # noqa: E402

MODULE_ROOT = Path(__file__).resolve().parents[2]
QUERY_FILE = MODULE_ROOT / "queries" / "q03.sql"
BASELINE_FILE = MODULE_ROOT / "baseline-local.json"
QUERY_ID = "q03"
MIN_SPEEDUP = 100.0


def leading_column(cur, index_name):
    cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s", (index_name,))
    row = cur.fetchone()
    if row is None:
        return None
    m = re.search(r"\(([^)]+)\)", row[0])
    if not m:
        return None
    return m.group(1).split(",")[0].strip().split()[0]


def main():
    sql = QUERY_FILE.read_text(encoding="utf-8")

    try:
        plan = get_plan(sql)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not run query: {e}")
        sys.exit(1)

    try:
        forbid_node(plan, "Seq Scan", table="order_items")
        print("PASS  no Seq Scan on order_items")
    except PlanAssertionError as e:
        print(f"FAIL  {e}")
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    try:
        hits = require_node(plan, "Index Scan", table="order_items")
        print("PASS  order_items reached via an index")
    except PlanAssertionError as e:
        print(f"FAIL  {e}")
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    try:
        with psycopg.connect(conninfo()) as conn:
            with conn.cursor() as cur:
                leading_ok = False
                checked = []
                for node in hits:
                    idx = node.get("Index Name")
                    if not idx:
                        continue
                    col = leading_column(cur, idx)
                    checked.append(f"{idx} (leads with {col})")
                    if col == "order_id":
                        leading_ok = True
    except psycopg.Error as e:
        print(f"NOT PASSED: could not inspect pg_indexes: {e}")
        sys.exit(1)

    if leading_ok:
        print("PASS  order_items index leads with order_id")
    else:
        reason = (
            "order_items is reached via an index, but none of them lead with "
            f"order_id (checked: {', '.join(checked) or 'none'}). An index that "
            "merely contains order_id is not enough — it must be the leading "
            "column for an order_id equality filter to use it efficiently."
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    if not BASELINE_FILE.exists() or QUERY_ID not in baseline.load_baseline(BASELINE_FILE):
        reason = f"record the baseline first: uv run python tools/baseline.py record queries/{QUERY_ID}.sql"
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    data = baseline.load_baseline(BASELINE_FILE)
    base_ms = data[QUERY_ID]["median_ms"]
    try:
        timings = baseline.time_query(sql, runs=5, warmups=1)
    except psycopg.Error as e:
        print(f"NOT PASSED: timing run failed: {e}")
        sys.exit(1)
    import statistics

    median = statistics.median(timings)
    speedup = base_ms / median if median > 0 else float("inf")
    if speedup >= MIN_SPEEDUP:
        print(f"PASS  {median:.2f} ms vs baseline {base_ms:.2f} ms -> {speedup:.1f}x speedup (required >= {MIN_SPEEDUP}x)")
    else:
        reason = (
            f"{median:.2f} ms vs baseline {base_ms:.2f} ms -> only {speedup:.1f}x speedup "
            f"(required >= {MIN_SPEEDUP}x)"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
