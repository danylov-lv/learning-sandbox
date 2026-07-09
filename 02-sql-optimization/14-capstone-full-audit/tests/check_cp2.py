"""Checkpoint 2 checker for 14-capstone-full-audit: fix the hot paths.

Run from the module root:
    uv run python 14-capstone-full-audit/tests/check_cp2.py

For each workload/qcNN.sql, this asserts:
  1. A structural plan gate (per-query -- see PLAN_GATES below), run via
     tools/plan_check.py against the query as it stands in the live database.
  2. A relative timing gate against tools/baseline.py's baseline-local.json,
     EXCEPT where noted secondary/info (see docstrings on individual gate
     functions below).

This checker does not care *how* you fixed each query (DDL, ANALYZE,
partitioning, ...) -- only that the resulting plan and timing look like a
fixed query, not a stock one. It re-reads workload/qcNN.sql live each run.
"""

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
TASK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "tools"))

import psycopg  # noqa: E402

from plan_check import (  # noqa: E402
    PlanAssertionError,
    conninfo,
    find_nodes,
    get_plan,
    require_node,
    forbid_node,
)
import baseline  # noqa: E402

BASELINE_FILE = MODULE_ROOT / "baseline-local.json"

# Roughly 1/4 of the measured reference-fix speedup, per module convention,
# except where a query's real fix only buys a modest speedup (qc04, qc06) --
# there the bar is set below the weaker verified variant with margin instead,
# and qc03/qc05 have no hard timing gate at all (see their gate functions).
MIN_SPEEDUP = {
    "qc01": 50.0,
    "qc02": 100.0,
    "qc04": 1.5,
    "qc06": 1.3,
    "qc07": 30.0,
    "qc08": 20.0,
}

MAX_ESTIMATE_ERROR_QC05 = 50.0
MAX_SCANNED_PARTITIONS_QC03 = 8


def sql_of(qid):
    return (TASK_ROOT / "workload" / f"{qid}.sql").read_text(encoding="utf-8")


def gate_qc01(plan):
    forbid_node(plan, "Seq Scan", table="orders")
    require_node(plan, "Index Scan", table="orders")


def gate_qc02(plan):
    forbid_node(plan, "Seq Scan", table="order_items")
    require_node(plan, "Index Scan", table="order_items")


def gate_qc03(plan, cur):
    """Accept either fix family for the inventory_events recent-window query:

    (a) a proper index -- distinguishing signal is an Index Only Scan node on
        inventory_events, which the stock plan (a plain Index Scan over the
        single-column occurred_at index) never produces; or
    (b) partitioning -- distinguishing signal is that inventory_events is now
        a partitioned table (pg_partitioned_table) AND the plan only touches
        a small number of partitions (an open-ended lower-bound predicate
        with no upper bound will still show any future headroom partitions
        as scanned nodes -- see .authoring/tasks-w4-capstone.md -- so the
        bound here is generous, not a tight pruning-to-2 requirement).
    """
    ios_hits = find_nodes(plan, "Index Only Scan", table="inventory_events")
    if ios_hits:
        return "index-only-scan"

    cur.execute(
        "SELECT c.oid FROM pg_class c JOIN pg_partitioned_table pt ON pt.partrelid = c.oid "
        "WHERE c.relname = 'inventory_events'"
    )
    row = cur.fetchone()
    if row is None:
        raise PlanAssertionError(
            "no Index Only Scan on inventory_events, and inventory_events is not a "
            "partitioned table -- neither accepted fix family is present"
        )

    def relnames(node):
        names = set()
        if node.get("Relation Name"):
            names.add(node["Relation Name"])
        for child in node.get("Plans", []):
            names |= relnames(child)
        return names

    scanned = relnames(plan["Plan"])
    cur.execute(
        """
        SELECT count(*) FROM pg_inherits i
        JOIN pg_class child ON child.oid = i.inhrelid
        WHERE i.inhparent = %s AND child.relname = ANY(%s)
        """,
        (row[0], list(scanned)),
    )
    touched = cur.fetchone()[0]
    if touched > MAX_SCANNED_PARTITIONS_QC03:
        raise PlanAssertionError(
            f"inventory_events is partitioned but the plan still touches {touched} "
            f"partitions (> {MAX_SCANNED_PARTITIONS_QC03}) -- pruning isn't working"
        )
    return f"partition-pruning ({touched} partitions touched)"


def gate_qc04(plan):
    forbid_node(plan, "Seq Scan", table="products")
    # Not scoped by table=: a GIN-index fix here reliably produces a Bitmap
    # Heap Scan / Bitmap Index Scan pair, and (same caveat documented in
    # 02-support-dashboard/tests/check.py) Bitmap Index Scan nodes never
    # carry their own Relation Name/Alias, so a table= qualifier can't match
    # them. Safe here: single-table query, forbid_node above is still scoped.
    require_node(plan, "Index Scan")


def gate_qc05(plan):
    """Worst row-estimate error, skipping BitmapAnd/BitmapOr nodes.

    tools/plan_check.py's rows_estimate_error() looks at every node's
    Actual Rows vs Plan Rows, but BitmapAnd/BitmapOr nodes report
    Actual Rows = 0 unconditionally (they combine bitmaps, they don't
    produce tuples), which manufactures a spurious multi-thousand-x
    "error" whenever the reference fix's second index (orders.created_at,
    built for qc06/07/08) happens to combine with idx_orders_status via a
    BitmapAnd -- verified in .authoring/tasks-w4-capstone.md. Skipping
    those two node types and taking the worst of what remains reflects
    what the planner actually believes about orders.status.
    """
    worst, worst_node = 1.0, None
    for node in _iter_nodes(plan):
        if node.get("Node Type") in ("BitmapAnd", "BitmapOr"):
            continue
        if "Actual Rows" not in node or "Plan Rows" not in node:
            continue
        actual = max(node["Actual Rows"] * max(node.get("Actual Loops", 1), 1), 1)
        est = max(node["Plan Rows"], 1)
        factor = max(actual / est, est / actual)
        if factor > worst:
            worst, worst_node = factor, node
    where = f"{worst_node.get('Node Type')} on {worst_node.get('Relation Name', '?')}" if worst_node else "-"
    if worst > MAX_ESTIMATE_ERROR_QC05:
        raise PlanAssertionError(
            f"worst row-estimate error {worst:.1f}x > {MAX_ESTIMATE_ERROR_QC05}x ({where}) "
            "-- pg_stats on orders.status still looks stale"
        )
    return worst


def _iter_nodes(plan):
    root = plan["Plan"] if "Plan" in plan else plan
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("Plans", []))


def gate_qc06(plan):
    """The reference fix (an index on orders.created_at) reliably keeps
    orders off a Seq Scan, but whether the planner chooses a Nested Loop or a
    Hash Join for the payments side afterwards depends on whether ANALYZE has
    also run recently -- both are legitimate, verified plan shapes (see
    .authoring/tasks-w4-capstone.md). So this gate only pins down the orders
    side; it deliberately does not forbid a Seq Scan on payments."""
    forbid_node(plan, "Seq Scan", table="orders")
    require_node(plan, "Index Scan", table="orders")


def gate_qc07(plan):
    forbid_node(plan, "Seq Scan", table="orders")
    require_node(plan, "Index Scan", table="orders")


def gate_qc08(plan):
    forbid_node(plan, "Seq Scan", table="order_items")
    forbid_node(plan, "Seq Scan", table="orders")
    require_node(plan, "Index Scan", table="order_items")


def check_query(qid, cur, failures):
    sql = sql_of(qid)
    try:
        plan = get_plan(sql)
    except psycopg.Error as e:
        failures.append(f"{qid}: could not run query: {e}")
        print(f"FAIL  {qid}: could not run query: {e}")
        return

    try:
        if qid == "qc01":
            gate_qc01(plan)
        elif qid == "qc02":
            gate_qc02(plan)
        elif qid == "qc03":
            info = gate_qc03(plan, cur)
            print(f"info  {qid}: accepted fix family -- {info}")
        elif qid == "qc04":
            gate_qc04(plan)
        elif qid == "qc05":
            factor = gate_qc05(plan)
            print(f"PASS  {qid}: worst row-estimate error {factor:.1f}x <= {MAX_ESTIMATE_ERROR_QC05}x")
        elif qid == "qc06":
            gate_qc06(plan)
        elif qid == "qc07":
            gate_qc07(plan)
        elif qid == "qc08":
            gate_qc08(plan)
    except PlanAssertionError as e:
        failures.append(f"{qid}: {e}")
        print(f"FAIL  {qid}: {e}")
        return

    if qid != "qc05":
        print(f"PASS  {qid}: plan structure looks fixed")

    if qid in ("qc03", "qc05"):
        # informational timing only, per this query's design (see gate docstrings)
        try:
            base = baseline.load_baseline(BASELINE_FILE)
            if qid in base:
                timings = baseline.time_query(sql, runs=5)
                import statistics

                median = statistics.median(timings)
                print(f"info  {qid}: median {median:.1f} ms (baseline {base[qid]['median_ms']:.1f} ms)")
        except psycopg.Error as e:
            print(f"info  {qid}: could not time query for info: {e}")
        return

    if qid not in MIN_SPEEDUP:
        return

    if not BASELINE_FILE.exists():
        failures.append(f"{qid}: no baseline-local.json -- run baseline.py record for all qc queries first")
        print(f"FAIL  {qid}: no baseline recorded")
        return

    base = baseline.load_baseline(BASELINE_FILE)
    if qid not in base:
        failures.append(f"{qid}: no baseline recorded for '{qid}' -- run baseline.py record on the stock query first")
        print(f"FAIL  {qid}: no baseline recorded for '{qid}'")
        return

    base_ms = base[qid]["median_ms"]
    try:
        timings = baseline.time_query(sql, runs=5)
    except psycopg.Error as e:
        failures.append(f"{qid}: could not time query: {e}")
        print(f"FAIL  {qid}: could not time query: {e}")
        return

    import statistics

    median = statistics.median(timings)
    speedup = base_ms / median if median > 0 else float("inf")
    required = MIN_SPEEDUP[qid]
    line = f"{qid}: median {median:.2f} ms vs baseline {base_ms:.2f} ms -> speedup {speedup:.1f}x (required >= {required}x)"
    if speedup >= required:
        print(f"PASS  {line}")
    else:
        failures.append(line)
        print(f"FAIL  {line}")


def main():
    try:
        conn = psycopg.connect(conninfo())
    except psycopg.Error as e:
        print(f"NOT PASSED: could not connect to the database: {e}")
        sys.exit(1)

    failures = []
    with conn.cursor() as cur:
        for qid in ["qc01", "qc02", "qc03", "qc04", "qc05", "qc06", "qc07", "qc08"]:
            check_query(qid, cur, failures)
    conn.rollback()
    conn.close()

    if failures:
        print(f"NOT PASSED: {'; '.join(failures)}")
        sys.exit(1)

    print("PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
