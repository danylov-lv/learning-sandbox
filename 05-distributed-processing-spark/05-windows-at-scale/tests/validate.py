"""Validator for 05-windows-at-scale.

Needs a live SparkSession, so it runs inside the container:
    ./run.sh 05-windows-at-scale/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    RAW_EVENTS_DIR,
    check_notes_filled,
    fail,
    get_plan,
    guarded,
    load_ground_truth,
    load_learner_module,
    passed,
    plan_has,
)

PRICE_TOL = 0.01


def _round_price(p):
    return None if p is None else round(float(p), 2)


def _reference_price_change(spark, events_df):
    """Validator-owned reference for price_change_per_product, groupBy/join only.

    Deliberately avoids any window function: find each product's latest
    observation via groupBy(max(captured_at)) + join, then find the
    "previous" observation by excluding the latest row and repeating the
    same groupBy(max(captured_at)) + join on what's left. Two independent
    formulations of the same "previous snapshot" question had better agree.
    """
    from pyspark.sql import functions as F

    valid = events_df.filter(F.col("http_status") == 200).select(
        "product_id", "price", "captured_at"
    )

    latest_ts = valid.groupBy("product_id").agg(F.max("captured_at").alias("captured_at"))
    latest = latest_ts.join(valid, ["product_id", "captured_at"]).select(
        "product_id",
        F.col("captured_at").alias("latest_captured_at"),
        F.col("price").alias("latest_price"),
    )

    remainder = valid.join(latest_ts, ["product_id", "captured_at"], "left_anti")

    prev_ts = remainder.groupBy("product_id").agg(F.max("captured_at").alias("captured_at"))
    prev = prev_ts.join(remainder, ["product_id", "captured_at"]).select(
        "product_id",
        F.col("captured_at").alias("prev_captured_at"),
        F.col("price").alias("prev_price"),
    )

    out = latest.join(prev, "product_id", "left")
    out = out.withColumn("price_delta", F.col("latest_price") - F.col("prev_price"))
    return {
        row["product_id"]: (
            _round_price(row["latest_price"]),
            row["latest_captured_at"],
            _round_price(row["prev_price"]),
            row["prev_captured_at"],
            _round_price(row["price_delta"]),
        )
        for row in out.collect()
    }


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()

    mod = load_learner_module(TASK_ROOT / "src" / "windows.py", "windows")
    for fn in ("prepare_events", "top_n_per_source", "price_change_per_product", "window_vs_aggregate_plans"):
        if not hasattr(mod, fn):
            fail(f"src/windows.py has no {fn}(...) function")

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.appName("05-windows-validate").master("local[*]").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")

    try:
        events = mod.prepare_events(spark, RAW_EVENTS_DIR)
        events.cache()
        events.count()

        expected_cols = {"product_id", "source_id", "price", "http_status", "captured_at"}
        if set(events.columns) != expected_cols:
            fail(f"prepare_events columns {sorted(events.columns)} != expected {sorted(expected_cols)}")

        # --- top_n_per_source ---
        n = gt["top_n_per_source"]["n"]
        topn = mod.top_n_per_source(spark, events, n)
        expected_topn_cols = {"source_id", "product_id", "price", "rn"}
        if set(topn.columns) != expected_topn_cols:
            fail(f"top_n_per_source columns {sorted(topn.columns)} != expected {sorted(expected_topn_cols)}")

        topn_plan = get_plan(topn)
        if not plan_has(topn_plan, "Window"):
            fail("top_n_per_source's plan has no Window node — this must be implemented with a window function")

        rows = topn.collect()
        by_source = {}
        for row in rows:
            sid = str(row["source_id"])
            by_source.setdefault(sid, []).append((row["rn"], _round_price(row["price"]), row["product_id"]))

        expected_by_source = gt["top_n_per_source"]["by_source"]
        if set(by_source.keys()) != set(expected_by_source.keys()):
            fail(
                f"top_n_per_source covers sources {sorted(by_source.keys())}, "
                f"expected {sorted(expected_by_source.keys())}"
            )

        for sid, expected_list in expected_by_source.items():
            got_sorted = [t[1:] for t in sorted(by_source[sid], key=lambda t: t[0])]
            expected_sorted = [(_round_price(e["price"]), e["product_id"]) for e in expected_list]
            rns = sorted(t[0] for t in by_source[sid])
            if rns != list(range(1, n + 1)):
                fail(f"top_n_per_source source {sid}: rn values {rns} != expected 1..{n} (exactly {n} rows)")
            if got_sorted != expected_sorted:
                fail(
                    f"top_n_per_source source {sid}: got {got_sorted}, "
                    f"expected {expected_sorted} (order + values must match ground-truth.json exactly)"
                )

        # --- price_change_per_product ---
        pcp = mod.price_change_per_product(spark, events)
        expected_pcp_cols = {
            "product_id", "latest_price", "latest_captured_at",
            "prev_price", "prev_captured_at", "price_delta",
        }
        if set(pcp.columns) != expected_pcp_cols:
            fail(f"price_change_per_product columns {sorted(pcp.columns)} != expected {sorted(expected_pcp_cols)}")

        learner_map = {
            row["product_id"]: (
                _round_price(row["latest_price"]),
                row["latest_captured_at"],
                _round_price(row["prev_price"]),
                row["prev_captured_at"],
                _round_price(row["price_delta"]),
            )
            for row in pcp.collect()
        }
        reference_map = _reference_price_change(spark, events)

        if set(learner_map.keys()) != set(reference_map.keys()):
            missing = set(reference_map.keys()) - set(learner_map.keys())
            extra = set(learner_map.keys()) - set(reference_map.keys())
            fail(
                f"price_change_per_product product_id set differs from the groupBy/join reference "
                f"(missing {len(missing)}, extra {len(extra)}) — sample missing: {list(missing)[:5]}, "
                f"sample extra: {list(extra)[:5]}"
            )

        mismatches = []
        for pid, ref_tuple in reference_map.items():
            got_tuple = learner_map[pid]
            for (g, r) in zip(got_tuple, ref_tuple):
                if isinstance(r, float) or isinstance(g, float):
                    if r is None or g is None:
                        if r is not g:
                            mismatches.append((pid, got_tuple, ref_tuple))
                            break
                    elif abs(g - r) > PRICE_TOL:
                        mismatches.append((pid, got_tuple, ref_tuple))
                        break
                elif g != r:
                    mismatches.append((pid, got_tuple, ref_tuple))
                    break
            if len(mismatches) >= 5:
                break

        if mismatches:
            fail(
                f"price_change_per_product disagrees with the validator's independent groupBy/join reference "
                f"on {len(mismatches)}+ products, e.g. {mismatches[:3]} "
                f"(format: product_id, (latest_price, latest_captured_at, prev_price, prev_captured_at, price_delta))"
            )

        # --- window_vs_aggregate_plans ---
        wap = mod.window_vs_aggregate_plans(spark, events)
        if not isinstance(wap, dict):
            fail(f"window_vs_aggregate_plans must return a dict, got {type(wap).__name__}")
        for key in ("window_plan", "aggregate_plan", "window_max_price_by_source", "aggregate_max_price_by_source"):
            if key not in wap:
                fail(f"window_vs_aggregate_plans result missing key '{key}'")

        window_plan = wap["window_plan"]
        aggregate_plan = wap["aggregate_plan"]

        if not plan_has(window_plan, "Window"):
            fail("window_vs_aggregate_plans's window_plan has no Window node")
        if not (plan_has(window_plan, "Exchange") or plan_has(window_plan, "Sort")):
            fail(
                "window_vs_aggregate_plans's window_plan has no Exchange/Sort node — "
                "expected a full shuffle-and-sort by the partitionBy key"
            )
        if plan_has(aggregate_plan, "Window"):
            fail("window_vs_aggregate_plans's aggregate_plan has a Window node — expected groupBy/agg only, no window")

        expected_max_by_source = {
            sid: _round_price(entries[0]["price"]) for sid, entries in expected_by_source.items()
        }

        for label in ("window_max_price_by_source", "aggregate_max_price_by_source"):
            got_max = {str(k): _round_price(v) for k, v in wap[label].items()}
            if set(got_max.keys()) != set(expected_max_by_source.keys()):
                fail(f"{label} covers sources {sorted(got_max.keys())}, expected {sorted(expected_max_by_source.keys())}")
            for sid, expected_price in expected_max_by_source.items():
                if got_max[sid] != expected_price:
                    fail(
                        f"{label}[{sid}] = {got_max[sid]}, expected {expected_price} "
                        "(ground-truth.json's top_n_per_source.by_source[source][0].price)"
                    )

    finally:
        spark.stop()

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed("top-n leaderboard, lag-based price change, and window-vs-aggregate plans all check out")


if __name__ == "__main__":
    main()
