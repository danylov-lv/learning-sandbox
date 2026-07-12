"""Validator for 10-nosql-patterns task 06 -- mongodb-vs-jsonb.

Runs the SAME workload against both engines and checks THREE independent
things about the learner's src/both.py:

  1. Correctness -- mongo_containment/pg_containment must each reproduce
     data/ground-truth.json's graded_query exactly (count + product_ids
     set); mongo_nested_color/pg_nested_color("black") must each match
     nested_query.count exactly.
  2. Fair indexing (the crux) -- the containment query must be answered
     WITHOUT a sequential scan on either side: EXPLAIN on Postgres must show
     no Seq Scan on t06.products, and explain("queryPlanner") on Mongo must
     show IXSCAN and no COLLSCAN. Correctness with a full scan does not
     count -- this is the whole point of comparing "properly indexed
     MongoDB" against "properly indexed Postgres JSONB", not either engine
     running unindexed.
  3. Partial update -- updating one product's price on each side must be
     reflected when re-queried, proving jsonb_set / $set worked in place.

Run from this task's directory:

    uv run python tests/validate.py
"""

import copy
import json
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
    pg_connect,
)
from src.both import (  # noqa: E402
    mongo_containment,
    mongo_create_indexes,
    mongo_load,
    mongo_nested_color,
    mongo_partial_update,
    pg_containment,
    pg_create_indexes,
    pg_load,
    pg_nested_color,
    pg_partial_update,
    pg_setup,
)

NESTED_COLOR = "black"
UPDATE_PRODUCT_ID = 1
UPDATE_NEW_PRICE = 999.99

CONTAINMENT_FILTER = {"category": "electronics", "in_stock": True, "tags": "sale"}
CONTAINMENT_JSONB = json.dumps(
    {"category": "electronics", "in_stock": True, "tags": ["sale"]}
)


def _load_products():
    products = []
    with open(PRODUCTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                products.append(json.loads(line))
    return products


def _mongo_stage_names(plan):
    """Recursively collect every 'stage' value in a Mongo explain() plan,
    walking inputStage / inputStages / shards so nested compound plans are
    covered."""
    stages = []

    def walk(node):
        if isinstance(node, dict):
            if "stage" in node:
                stages.append(node["stage"])
            for key in ("inputStage", "queryPlan"):
                if key in node:
                    walk(node[key])
            for key in ("inputStages", "shards"):
                if key in node:
                    for child in node[key]:
                        walk(child)
            for key, value in node.items():
                if key not in (
                    "inputStage",
                    "inputStages",
                    "shards",
                    "queryPlan",
                    "stage",
                ) and isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(plan.get("queryPlanner", {}).get("winningPlan", {}))
    return stages


@guarded
def main():
    gt = load_ground_truth()
    expected_containment = gt["graded_query"]
    expected_nested_count = gt["nested_query"]["count"]

    products = _load_products()
    if not products:
        not_passed(f"no products loaded from {PRODUCTS_PATH}")

    # --- Setup: reset both namespaces, load, index -----------------------
    # pymongo's insert_many mutates each dict in place (adds "_id"), so each
    # side gets its own deep copy to keep the two loads fully independent.
    db = mongo_db()
    db.drop_collection("t06_products")
    mongo_load(db, copy.deepcopy(products))
    mongo_create_indexes(db)

    conn = pg_connect()
    pg_setup(conn)
    pg_load(conn, copy.deepcopy(products))
    pg_create_indexes(conn)

    # --- 1. Correctness: containment, both sides --------------------------
    mongo_result = mongo_containment(db)
    if int(mongo_result.get("count", -1)) != expected_containment["count"]:
        not_passed(
            f"mongo_containment() count={mongo_result.get('count')!r}, expected "
            f"{expected_containment['count']}"
        )
    if sorted(mongo_result.get("product_ids", [])) != sorted(expected_containment["product_ids"]):
        not_passed("mongo_containment() product_ids do not match ground truth's set exactly")

    pg_result = pg_containment(conn)
    if int(pg_result.get("count", -1)) != expected_containment["count"]:
        not_passed(
            f"pg_containment() count={pg_result.get('count')!r}, expected "
            f"{expected_containment['count']}"
        )
    if sorted(pg_result.get("product_ids", [])) != sorted(expected_containment["product_ids"]):
        not_passed("pg_containment() product_ids do not match ground truth's set exactly")

    # --- 1b. Correctness: nested match, both sides -------------------------
    mongo_nested = mongo_nested_color(db, NESTED_COLOR)
    if int(mongo_nested) != expected_nested_count:
        not_passed(
            f"mongo_nested_color({NESTED_COLOR!r}) = {mongo_nested}, expected "
            f"{expected_nested_count}"
        )

    pg_nested = pg_nested_color(conn, NESTED_COLOR)
    if int(pg_nested) != expected_nested_count:
        not_passed(
            f"pg_nested_color({NESTED_COLOR!r}) = {pg_nested}, expected "
            f"{expected_nested_count}"
        )

    # --- 2. Fair indexing: Postgres containment must avoid Seq Scan -------
    with conn.cursor() as cur:
        cur.execute(
            "EXPLAIN SELECT product_id FROM t06.products WHERE doc @> %s::jsonb",
            (CONTAINMENT_JSONB,),
        )
        plan_text = "\n".join(row[0] for row in cur.fetchall())
    if "Seq Scan" in plan_text:
        not_passed(
            "Postgres containment query plan contains a Seq Scan on t06.products -- "
            "expected a GIN index (created in pg_create_indexes) to serve the `@>` "
            f"containment filter instead. Plan:\n{plan_text}"
        )
    if "Bitmap Index Scan" not in plan_text and "Index Scan" not in plan_text:
        not_passed(
            "Postgres containment query plan shows no index scan of any kind -- "
            f"expected a GIN-backed Bitmap Index Scan. Plan:\n{plan_text}"
        )

    # --- 2b. Fair indexing: Mongo containment must avoid COLLSCAN ----------
    mongo_plan = db.t06_products.find(CONTAINMENT_FILTER).explain()
    stages = _mongo_stage_names(mongo_plan)
    if "COLLSCAN" in stages:
        not_passed(
            f"Mongo containment query plan uses COLLSCAN (stages={stages}) -- expected "
            "an index (built in mongo_create_indexes) to serve the filter instead"
        )
    if "IXSCAN" not in stages:
        not_passed(
            f"Mongo containment query plan does not use IXSCAN (stages={stages}) -- "
            "expected an index scan"
        )

    # --- 3. Partial update, both sides --------------------------------------
    mongo_partial_update(db, UPDATE_PRODUCT_ID, UPDATE_NEW_PRICE)
    mongo_doc = db.t06_products.find_one({"product_id": UPDATE_PRODUCT_ID})
    if mongo_doc is None:
        not_passed(f"product_id={UPDATE_PRODUCT_ID} not found in t06_products after update")
    if abs(float(mongo_doc["price"]) - UPDATE_NEW_PRICE) > 1e-6:
        not_passed(
            f"mongo_partial_update() did not stick -- price={mongo_doc.get('price')!r}, "
            f"expected {UPDATE_NEW_PRICE}"
        )
    if "specs" not in mongo_doc or "tags" not in mongo_doc:
        not_passed(
            "mongo_partial_update() appears to have clobbered other fields -- "
            "expected specs/tags to remain present"
        )

    pg_partial_update(conn, UPDATE_PRODUCT_ID, UPDATE_NEW_PRICE)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc FROM t06.products WHERE product_id = %s", (UPDATE_PRODUCT_ID,)
        )
        row = cur.fetchone()
    if row is None:
        not_passed(f"product_id={UPDATE_PRODUCT_ID} not found in t06.products after update")
    pg_doc = row[0]
    if abs(float(pg_doc["price"]) - UPDATE_NEW_PRICE) > 1e-6:
        not_passed(
            f"pg_partial_update() did not stick -- price={pg_doc.get('price')!r}, "
            f"expected {UPDATE_NEW_PRICE}"
        )
    if "specs" not in pg_doc or "tags" not in pg_doc:
        not_passed(
            "pg_partial_update() appears to have clobbered other fields -- "
            "expected specs/tags to remain present"
        )

    conn.close()
    passed(
        f"containment count={expected_containment['count']} matched on both sides; "
        f"nested_color({NESTED_COLOR!r})={expected_nested_count} matched on both sides; "
        "Postgres containment used an index (no Seq Scan), Mongo containment used "
        "IXSCAN (no COLLSCAN); partial update verified on both sides"
    )


if __name__ == "__main__":
    main()
