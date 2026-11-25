"""CP2 validator for the s09 capstone -- DuckDB cross-check over the Parquet
lake.

Pure lake, no ClickHouse involved. Opens a DuckDB connection over the
Hive-partitioned Parquet lake and checks:

  1. total_price_sum() matches data/ground-truth.json's price_sum within
     0.01 -- the same number CP1 checked, now computed by a different engine
     over a different physical copy of the data.
  2. per_category_instock() matches ground truth's per_category_instock
     (count exact, avg within 0.01, category set matching exactly).
  3. top_sellers() matches ground truth's top_sellers_by_count exactly, in
     order -- the same list CP1 checked.
  4. one_category_files(con, "electronics") returns EXACTLY ONE file path,
     and that path contains "category=electronics" -- proof the other 7
     partitions were pruned instead of scanned.

Fails cleanly if no Parquet lake is found on disk.

Run from this task's directory:

    uv run python tests/validate_cp2.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "src"))

from harness.common import (  # noqa: E402
    PARQUET_DIR,
    duckdb_connect,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)

import lake_check  # noqa: E402

PRICE_SUM_TOLERANCE = 0.01
AVG_TOLERANCE = 0.01
PROBE_CATEGORY = "electronics"


@guarded
def main():
    if not PARQUET_DIR.exists() or not any(PARQUET_DIR.glob("category=*/*.parquet")):
        not_passed(
            f"no Parquet lake found at {PARQUET_DIR} -- generate one at a light "
            "scale first, e.g. `SCALE=0.01 uv run python generate.py` from the "
            "module root"
        )

    gt = load_ground_truth()

    con = duckdb_connect()
    try:
        # 1. Grand total price sum.
        total = lake_check.total_price_sum(con)
        if not isinstance(total, (int, float)):
            not_passed(f"total_price_sum() returned {total!r}, expected a number")
        if abs(float(total) - gt["price_sum"]) > PRICE_SUM_TOLERANCE:
            not_passed(
                f"total_price_sum()={total}, expected {gt['price_sum']} within {PRICE_SUM_TOLERANCE}"
            )

        # 2. Per-category in-stock count + avg.
        expected_cat = gt["per_category_instock"]
        got_cat = lake_check.per_category_instock(con)
        if not got_cat:
            not_passed("per_category_instock() returned nothing")

        missing_cat = [c for c in expected_cat if c not in got_cat]
        if missing_cat:
            not_passed(f"per_category_instock() is missing categories: {missing_cat}")
        extra_cat = [c for c in got_cat if c not in expected_cat]
        if extra_cat:
            not_passed(f"per_category_instock() has unexpected categories: {extra_cat}")

        for cat, exp in expected_cat.items():
            count, avg = got_cat[cat]
            if int(count) != exp["count"]:
                not_passed(
                    f"per_category_instock(): category={cat!r} count={count}, "
                    f"expected {exp['count']} exactly"
                )
            if abs(float(avg) - exp["avg"]) > AVG_TOLERANCE:
                not_passed(
                    f"per_category_instock(): category={cat!r} avg={avg}, "
                    f"expected {exp['avg']} within {AVG_TOLERANCE}"
                )

        # 3. Top 10 sellers by observation count.
        expected_sellers = gt["top_sellers_by_count"]
        got_sellers = lake_check.top_sellers(con)
        got_sellers = [[int(sid), int(cnt)] for sid, cnt in got_sellers]
        if got_sellers != [[int(sid), int(cnt)] for sid, cnt in expected_sellers]:
            not_passed(
                f"top_sellers()={got_sellers}, expected {expected_sellers} exactly, in order"
            )

        # 4. Partition pruning proof.
        files = list(lake_check.one_category_files(con, PROBE_CATEGORY))
        if len(files) != 1:
            not_passed(
                f"one_category_files(con, {PROBE_CATEGORY!r}) returned "
                f"{len(files)} file(s): {files} -- expected exactly ONE (all "
                "other 7 partitions should have been pruned); check the WHERE "
                "clause filters on the partition column `category` and that "
                "hive_partitioning=true is set"
            )
        (only_file,) = files
        expected_fragment = f"category={PROBE_CATEGORY}"
        if expected_fragment not in str(only_file).replace("\\", "/"):
            not_passed(
                f"one_category_files(con, {PROBE_CATEGORY!r}) returned "
                f"{only_file!r}, which does not look like the "
                f"{expected_fragment} partition file"
            )

        passed(
            f"total_price_sum within {PRICE_SUM_TOLERANCE}; {len(expected_cat)} categories "
            f"matched per_category_instock; top {len(expected_sellers)} sellers matched "
            f"exactly; one_category_files({PROBE_CATEGORY!r}) pruned to exactly 1 file: "
            f"{only_file}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
