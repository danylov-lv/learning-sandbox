"""Checker for 04-index-only-scan.

Run from the module root:
    uv run python 04-index-only-scan/tests/check.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import PlanAssertionError, find_nodes, get_plan, require_node  # noqa: E402
import baseline  # noqa: E402

MODULE_ROOT = Path(__file__).resolve().parents[2]
QUERY_FILE = MODULE_ROOT / "queries" / "q04.sql"
BASELINE_FILE = MODULE_ROOT / "baseline-local.json"
QUERY_ID = "q04"
MIN_SPEEDUP = 50.0


def main():
    sql = QUERY_FILE.read_text(encoding="utf-8")

    try:
        plan = get_plan(sql)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not run query: {e}")
        sys.exit(1)

    try:
        require_node(plan, "Index Only Scan", table="orders")
        print("PASS  orders reached via an Index Only Scan")
    except PlanAssertionError as e:
        print(f"FAIL  {e}")
        print(f"NOT PASSED: {e}")
        sys.exit(1)

    # Informational only — not a pass/fail assertion. High Heap Fetches on
    # an Index Only Scan is expected on this table; see the task README.
    for node in find_nodes(plan, "Index Only Scan", table="orders"):
        fetches = node.get("Heap Fetches")
        rows = node.get("Actual Rows")
        print(f"info  Heap Fetches: {fetches} (rows returned by this node: {rows})")

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
