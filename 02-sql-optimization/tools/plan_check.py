"""EXPLAIN plan inspection: library + CLI.

Runs EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) inside a transaction that is
ALWAYS rolled back, so it is safe on UPDATE/DELETE statements too.

Library usage (for task tests):

    from plan_check import get_plan, forbid_node, require_node, require_join, rows_estimate_error

    plan = get_plan(open("queries/q01.sql").read())
    forbid_node(plan, "Seq Scan", table="orders")           # raises PlanAssertionError
    require_node(plan, "Index Scan", index="idx_orders_x")  # matches Index Only / Bitmap too
    require_join(plan, "Hash Join")
    factor, node = rows_estimate_error(plan)                # worst est-vs-actual factor

CLI usage:

    uv run python tools/plan_check.py queries/q01.sql \
        --forbid "Seq Scan:orders" --require "Index Scan:orders" --max-estimate-error 100

Assertion spec format "NodeType[:qualifier]" — the qualifier matches the
node's relation name, alias, or index name. Connection comes from PGHOST /
PGPORT / PGDATABASE / PGUSER / PGPASSWORD (defaults: localhost:54302,
sandbox/sandbox/sandbox).
"""

import argparse
import json
import os
import sys

import psycopg


class PlanAssertionError(AssertionError):
    pass


def conninfo():
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '54302')} "
        f"dbname={os.environ.get('PGDATABASE', 'sandbox')} "
        f"user={os.environ.get('PGUSER', 'sandbox')} "
        f"password={os.environ.get('PGPASSWORD', 'sandbox')}"
    )


def _strip_sql(sql):
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";")


def get_plan(sql, analyze=True, timeout_ms=300_000):
    """Return the EXPLAIN JSON top-level dict (keys: 'Plan', timings...)."""
    opts = "ANALYZE, BUFFERS, FORMAT JSON" if analyze else "FORMAT JSON"
    with psycopg.connect(conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
            cur.execute(f"EXPLAIN ({opts}) {_strip_sql(sql)}")
            result = cur.fetchone()[0]
        conn.rollback()
    if isinstance(result, str):
        result = json.loads(result)
    return result[0]


def iter_nodes(plan):
    """Yield every plan node dict, depth-first."""
    root = plan["Plan"] if "Plan" in plan else plan
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.get("Plans", []))


# require_node("Index Scan") should be satisfied by any index-driven access
_FAMILIES = {
    "Index Scan": {"Index Scan", "Index Only Scan", "Bitmap Index Scan"},
    "Index Only Scan": {"Index Only Scan"},
    "Bitmap Index Scan": {"Bitmap Index Scan"},
    "Seq Scan": {"Seq Scan"},
}


def _node_matches(node, node_type, table=None, index=None, family=False):
    types = _FAMILIES.get(node_type, {node_type}) if family else {node_type}
    if node.get("Node Type") not in types:
        return False
    if table is not None:
        if table not in (node.get("Relation Name"), node.get("Alias")):
            return False
    if index is not None and node.get("Index Name") != index:
        return False
    return True


def find_nodes(plan, node_type, table=None, index=None, family=False):
    return [n for n in iter_nodes(plan) if _node_matches(n, node_type, table, index, family)]


def _describe(node_type, table, index):
    parts = [node_type]
    if table:
        parts.append(f"on table '{table}'")
    if index:
        parts.append(f"using index '{index}'")
    return " ".join(parts)


def forbid_node(plan, node_type, table=None, index=None):
    """Assert NO node of this exact type (optionally scoped) is in the plan."""
    hits = find_nodes(plan, node_type, table, index, family=False)
    if hits:
        rels = {h.get("Relation Name") or h.get("Index Name") or "?" for h in hits}
        raise PlanAssertionError(
            f"forbidden node present: {_describe(node_type, table, index)} "
            f"(found {len(hits)}x on: {', '.join(sorted(rels))})"
        )


def require_node(plan, node_type, table=None, index=None):
    """Assert at least one matching node exists. 'Index Scan' also accepts
    Index Only Scan and Bitmap Index Scan."""
    hits = find_nodes(plan, node_type, table, index, family=True)
    if not hits:
        seen = sorted({n.get("Node Type", "?") for n in iter_nodes(plan)})
        raise PlanAssertionError(
            f"required node missing: {_describe(node_type, table, index)} "
            f"(plan contains: {', '.join(seen)})"
        )
    return hits


def require_join(plan, join_type):
    """join_type: 'Hash Join', 'Merge Join', or 'Nested Loop'."""
    return require_node(plan, join_type)


def rows_estimate_error(plan):
    """Worst-case planner misestimation factor across all nodes.

    Returns (factor, node). factor = max(actual/estimated, estimated/actual)
    computed with actual rows multiplied by loop count; 0-row cases use 1 as
    the floor so the factor stays finite.
    """
    worst, worst_node = 1.0, None
    for node in iter_nodes(plan):
        if "Actual Rows" not in node or "Plan Rows" not in node:
            continue
        actual = max(node["Actual Rows"] * max(node.get("Actual Loops", 1), 1), 1)
        est = max(node["Plan Rows"], 1)
        factor = max(actual / est, est / actual)
        if factor > worst:
            worst, worst_node = factor, node
    return worst, worst_node


def _parse_spec(spec):
    if ":" in spec:
        node_type, qual = spec.split(":", 1)
        return node_type.strip(), qual.strip()
    return spec.strip(), None


def _spec_hits(plan, node_type, qual, family):
    if qual is None:
        return find_nodes(plan, node_type, family=family)
    return (find_nodes(plan, node_type, table=qual, family=family)
            + find_nodes(plan, node_type, index=qual, family=family))


def main():
    ap = argparse.ArgumentParser(description="Assert on the EXPLAIN ANALYZE plan of a SQL file.")
    ap.add_argument("sql_file")
    ap.add_argument("--forbid", action="append", default=[], metavar="TYPE[:REL_OR_INDEX]")
    ap.add_argument("--require", action="append", default=[], metavar="TYPE[:REL_OR_INDEX]")
    ap.add_argument("--require-join", action="append", default=[], metavar="JOINTYPE")
    ap.add_argument("--max-estimate-error", type=float, default=None)
    ap.add_argument("--no-analyze", action="store_true", help="plain EXPLAIN (no execution)")
    ap.add_argument("--timeout-ms", type=int, default=300_000)
    args = ap.parse_args()

    sql = open(args.sql_file, encoding="utf-8").read()
    try:
        plan = get_plan(sql, analyze=not args.no_analyze, timeout_ms=args.timeout_ms)
    except psycopg.Error as e:
        print(f"FAIL  could not obtain plan: {e}")
        sys.exit(2)

    failed = False

    for spec in args.forbid:
        node_type, qual = _parse_spec(spec)
        hits = _spec_hits(plan, node_type, qual, family=False)
        if hits:
            print(f"FAIL  forbid {spec}: found {len(hits)} matching node(s)")
            failed = True
        else:
            print(f"PASS  forbid {spec}")

    for spec in args.require:
        node_type, qual = _parse_spec(spec)
        hits = _spec_hits(plan, node_type, qual, family=True)
        if hits:
            print(f"PASS  require {spec}")
        else:
            print(f"FAIL  require {spec}: no matching node in plan")
            failed = True

    for jt in args.require_join:
        try:
            require_join(plan, jt)
            print(f"PASS  require-join {jt}")
        except PlanAssertionError as e:
            print(f"FAIL  require-join {jt}: {e}")
            failed = True

    if args.max_estimate_error is not None:
        factor, node = rows_estimate_error(plan)
        where = f"{node.get('Node Type')} on {node.get('Relation Name', '?')}" if node else "-"
        if factor > args.max_estimate_error:
            print(f"FAIL  estimate error {factor:.1f}x > {args.max_estimate_error}x ({where})")
            failed = True
        else:
            print(f"PASS  estimate error {factor:.1f}x <= {args.max_estimate_error}x")

    if not args.no_analyze:
        ms = plan.get("Execution Time")
        if ms is not None:
            print(f"info  execution time: {ms:.1f} ms")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
