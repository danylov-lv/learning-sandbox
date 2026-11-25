"""Validator for 07-polars-calibration.

Purely host-side — no SparkSession needed, unlike most of this module's
validators (it only checks numbers, and harness.common imports pyspark
lazily so this stays importable without pyspark installed):
    uv run python 07-polars-calibration/tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    RAW_EVENTS_DIR,
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_learner_module,
    load_results,
    passed,
)

RESULTS_PATH = TASK_ROOT / "results-local.json"

# this task's deliverable is partly the writeup, so the bar for NOTES.md is higher
NOTES_MIN_CHARS = 700


@guarded
def main():
    if not RAW_EVENTS_DIR.exists() or not any(RAW_EVENTS_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_EVENTS_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()

    mod = load_learner_module(TASK_ROOT / "src" / "calibrate.py", "calibrate")
    for fn in ("load_events", "monthly_rollup", "filter_probe", "top3_per_source"):
        if not hasattr(mod, fn):
            fail(f"src/calibrate.py has no {fn}(...) function")

    import polars as pl

    # --- load_events ---
    lf = mod.load_events(RAW_EVENTS_DIR)
    if not isinstance(lf, pl.LazyFrame):
        fail(f"load_events must return a polars.LazyFrame, got {type(lf).__name__}")

    n_rows = lf.select(pl.len()).collect().item()
    if n_rows != gt["distinct_rows"]:
        fail(
            f"load_events produced {n_rows} rows, expected {gt['distinct_rows']} "
            "(ground-truth distinct_rows — malformed lines dropped, exact duplicates removed)"
        )

    # --- monthly_rollup ---
    monthly = mod.monthly_rollup(lf)
    if not isinstance(monthly, dict) or "rows_by_month" not in monthly or "price_sum_by_month" not in monthly:
        fail("monthly_rollup must return {'rows_by_month': {...}, 'price_sum_by_month': {...}}")

    rows_by_month = monthly["rows_by_month"]
    price_sum_by_month = monthly["price_sum_by_month"]
    expected_rbm = gt["rows_by_month"]
    expected_psbm = gt["price_sum_by_month"]

    if set(str(k) for k in rows_by_month.keys()) != set(expected_rbm.keys()):
        fail(f"rows_by_month keys {sorted(rows_by_month.keys())} != ground-truth keys {sorted(expected_rbm.keys())}")
    for k, v in expected_rbm.items():
        got = rows_by_month.get(k, rows_by_month.get(str(k)))
        if got is None or int(got) != int(v):
            fail(f"rows_by_month[{k}]={got}, expected {v}")
    for k, v in expected_psbm.items():
        got = price_sum_by_month.get(k, price_sum_by_month.get(str(k)))
        if got is None:
            fail(f"price_sum_by_month missing key '{k}'")
        approx(float(got), float(v), rel_tol=1e-6, what=f"price_sum_by_month[{k}]")

    # --- filter_probe ---
    probe = mod.filter_probe(lf)
    if not isinstance(probe, dict) or "rows" not in probe or "price_sum" not in probe:
        fail("filter_probe must return {'rows': int, 'price_sum': float}")

    expected_probe = gt["filter_probe"]
    if int(probe["rows"]) != expected_probe["rows"]:
        fail(f"filter_probe rows={probe['rows']}, expected {expected_probe['rows']}")
    approx(float(probe["price_sum"]), expected_probe["price_sum"], rel_tol=1e-6, what="filter_probe price_sum")

    # --- top3_per_source ---
    top3 = mod.top3_per_source(lf)
    if not isinstance(top3, dict):
        fail(f"top3_per_source must return a dict, got {type(top3).__name__}")

    expected_top3 = gt["top_n_per_source"]["by_source"]
    if set(str(k) for k in top3.keys()) != set(expected_top3.keys()):
        fail(f"top3_per_source keys {sorted(top3.keys())} != ground-truth keys {sorted(expected_top3.keys())}")

    for src, expected_list in expected_top3.items():
        got_list = top3.get(src, top3.get(int(src)))
        if got_list is None:
            fail(f"top3_per_source missing key '{src}'")
        if len(got_list) != len(expected_list):
            fail(f"top3_per_source[{src}] has {len(got_list)} entries, expected {len(expected_list)}")
        for i, (got, expected) in enumerate(zip(got_list, expected_list)):
            if int(got["product_id"]) != expected["product_id"] or abs(float(got["price"]) - expected["price"]) > 1e-6:
                fail(
                    f"top3_per_source[{src}][{i}] = {got}, expected {expected} "
                    "(order matters: price desc, ties broken by product_id desc)"
                )

    # --- timing presence (no ratio gate: the point is the learner sees both numbers) ---
    results = load_results(RESULTS_PATH, what="results-local.json")
    for key in ("polars", "spark"):
        if key not in results:
            how = (
                "uv run python 07-polars-calibration/tests/bench.py"
                if key == "polars"
                else "./run.sh 07-polars-calibration/tests/bench.py --spark"
            )
            fail(f"results-local.json missing '{key}' timing — run: {how}")
        entry = results[key]
        if not isinstance(entry, dict) or "wall_seconds" not in entry:
            fail(f"results-local.json['{key}'] missing 'wall_seconds'")
        if not (entry["wall_seconds"] > 0):
            fail(f"results-local.json['{key}']['wall_seconds']={entry['wall_seconds']}, expected > 0")

    check_notes_filled(TASK_ROOT / "NOTES.md", min_chars=NOTES_MIN_CHARS)

    passed(
        f"monthly rollup, filter probe, and top-3 per source all match ground truth "
        f"(polars={results['polars']['wall_seconds']:.2f}s, spark={results['spark']['wall_seconds']:.2f}s)"
    )


if __name__ == "__main__":
    main()
