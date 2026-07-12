"""Validator for 10-nosql-patterns task 05 -- mongodb-document-modeling.

Checks TWO independent things about the learner's src/model.py:

  1. Correctness -- per_category_stats(), top_brands(), graded_query(), and
     nested_color("black") must reproduce data/ground-truth.json's
     per_category / top_brands / graded_query / nested_query.
  2. Index usage (structural) -- the query shapes behind graded_query() and
     nested_color() must be answerable by MongoDB's query planner via an
     index (IXSCAN present in the winning plan) rather than a full
     collection scan (COLLSCAN). This is checked independently of the
     learner's own aggregation code, by running explain('queryPlanner') on
     the equivalent filter directly against `t05_products` -- proof that
     create_indexes() actually built something the planner picks for this
     exact query shape.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    PRODUCTS_PATH,
    guarded,
    load_ground_truth,
    mongo_db,
    not_passed,
    passed,
)
from src.model import (  # noqa: E402
    create_indexes,
    graded_query,
    load,
    nested_color,
    per_category_stats,
    top_brands,
)

COLLECTION = "t05_products"
AVG_TOLERANCE = 0.01

GRADED_FILTER = {"category": "electronics", "in_stock": True, "tags": "sale"}
NESTED_COLOR = "black"
NESTED_FILTER = {"specs.color": NESTED_COLOR}


def _read_products():
    import json

    if not PRODUCTS_PATH.exists():
        not_passed(f"products not found at {PRODUCTS_PATH} -- run `uv run python generate.py` first")
    products = []
    with PRODUCTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def _drop_t05_collections(db):
    for name in db.list_collection_names():
        if name.startswith("t05_"):
            db.drop_collection(name)


def _stage_names(plan_node, out):
    """Collect every 'stage' value found anywhere in a winningPlan tree,
    including nested inputStage/inputStages (compound/OR plans)."""
    if isinstance(plan_node, dict):
        if "stage" in plan_node:
            out.add(plan_node["stage"])
        for key in ("inputStage", "queryPlan"):
            if key in plan_node:
                _stage_names(plan_node[key], out)
        if "inputStages" in plan_node:
            for child in plan_node["inputStages"]:
                _stage_names(child, out)
    elif isinstance(plan_node, list):
        for item in plan_node:
            _stage_names(item, out)


def _assert_index_backed(db, filter_, label):
    explain = db.command(
        "explain",
        {"find": COLLECTION, "filter": filter_},
        verbosity="queryPlanner",
    )
    winning_plan = explain.get("queryPlanner", {}).get("winningPlan", {})
    stages = set()
    _stage_names(winning_plan, stages)

    if "COLLSCAN" in stages:
        not_passed(
            f"{label}: winning plan includes COLLSCAN (stages={sorted(stages)}) -- "
            f"query {filter_} is not index-backed; check create_indexes()"
        )
    if "IXSCAN" not in stages:
        not_passed(
            f"{label}: winning plan has no IXSCAN stage (stages={sorted(stages)}) -- "
            f"query {filter_} is not using an index; check create_indexes()"
        )
    return stages


@guarded
def main():
    gt = load_ground_truth()
    products = _read_products()

    db = mongo_db()
    _drop_t05_collections(db)

    load(db, products)
    create_indexes(db)

    # --- 1. per_category_stats() vs ground truth -------------------------
    expected_cat = gt["per_category"]
    got_rows = per_category_stats(db)
    if not got_rows:
        not_passed("per_category_stats() returned no rows")

    got_cat = {r["category"]: r for r in got_rows}
    missing = [c for c in expected_cat if c not in got_cat]
    if missing:
        not_passed(f"per_category_stats() is missing categories: {missing}")

    for cat, exp in expected_cat.items():
        row = got_cat[cat]
        if int(row["count"]) != exp["count"]:
            not_passed(
                f"per_category_stats(): category={cat!r} count={row['count']}, "
                f"expected {exp['count']} exactly"
            )
        if int(row["in_stock_count"]) != exp["in_stock_count"]:
            not_passed(
                f"per_category_stats(): category={cat!r} in_stock_count={row['in_stock_count']}, "
                f"expected {exp['in_stock_count']} exactly"
            )
        if abs(float(row["avg_price"]) - exp["avg_price"]) > AVG_TOLERANCE:
            not_passed(
                f"per_category_stats(): category={cat!r} avg_price={row['avg_price']}, "
                f"expected {exp['avg_price']} within {AVG_TOLERANCE}"
            )

    # --- 2. top_brands() vs ground truth ----------------------------------
    expected_brands = [tuple(b) for b in gt["top_brands"]]
    got_brands_raw = top_brands(db, n=10)
    got_brands = [tuple(b) for b in got_brands_raw]
    if got_brands != expected_brands:
        not_passed(
            f"top_brands() = {got_brands}, expected {expected_brands} exactly "
            "(order and ties matter)"
        )

    # --- 3. graded_query() vs ground truth --------------------------------
    expected_graded = gt["graded_query"]
    got_graded = graded_query(db)
    if int(got_graded.get("count", -1)) != expected_graded["count"]:
        not_passed(
            f"graded_query(): count={got_graded.get('count')}, "
            f"expected {expected_graded['count']} exactly"
        )
    got_ids = set(got_graded.get("product_ids", []))
    expected_ids = set(expected_graded["product_ids"])
    if got_ids != expected_ids:
        extra = got_ids - expected_ids
        missing_ids = expected_ids - got_ids
        not_passed(
            "graded_query(): product_ids mismatch "
            f"(extra={len(extra)}, missing={len(missing_ids)})"
        )

    # --- 4. nested_color("black") vs ground truth -------------------------
    expected_nested = gt["nested_query"]["count"]
    got_nested = nested_color(db, NESTED_COLOR)
    if int(got_nested) != expected_nested:
        not_passed(
            f"nested_color({NESTED_COLOR!r}) = {got_nested}, expected {expected_nested} exactly"
        )

    # --- 5. index usage (structural) --------------------------------------
    graded_stages = _assert_index_backed(db, GRADED_FILTER, "graded_query")
    nested_stages = _assert_index_backed(db, NESTED_FILTER, "nested_color")

    passed(
        f"correctness OK (per_category, top_brands, graded_query.count="
        f"{expected_graded['count']}, nested_query.count={expected_nested}); "
        f"index-backed: graded_query stages={sorted(graded_stages)}, "
        f"nested_color stages={sorted(nested_stages)}"
    )


if __name__ == "__main__":
    main()
