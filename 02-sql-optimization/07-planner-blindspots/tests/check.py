"""Checker for 07-planner-blindspots.

Run from the module root:
    uv run python 07-planner-blindspots/tests/check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import psycopg  # noqa: E402

from plan_check import PlanAssertionError, get_plan, require_node, rows_estimate_error  # noqa: E402

QUERY_FILE = Path(__file__).resolve().parents[1] / "src" / "given_query.sql"
MAX_ESTIMATE_ERROR = 1000.0


def main():
    sql = QUERY_FILE.read_text(encoding="utf-8")

    try:
        plan = get_plan(sql)
    except psycopg.Error as e:
        print(f"NOT PASSED: could not run query: {e}")
        sys.exit(1)

    factor, node = rows_estimate_error(plan)
    where = f"{node.get('Node Type')} on {node.get('Relation Name', '?')}" if node else "-"
    if factor <= MAX_ESTIMATE_ERROR:
        print(f"PASS  worst row-estimate error {factor:.1f}x <= {MAX_ESTIMATE_ERROR}x")
    else:
        reason = (
            f"worst row-estimate error {factor:.1f}x > {MAX_ESTIMATE_ERROR}x ({where}) "
            "-- the planner is still working from stale/insufficient statistics on orders.status"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    try:
        require_node(plan, "Memoize")
        print("PASS  planner trusts its estimate enough to add a Memoize node")
    except PlanAssertionError as e:
        reason = (
            f"{e} -- with accurate statistics the planner adds a Memoize node around "
            "the inner side of the join; its absence suggests the estimate is still off"
        )
        print(f"FAIL  {reason}")
        print(f"NOT PASSED: {reason}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
