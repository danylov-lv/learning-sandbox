"""Validator for 09-olap-clickhouse-duckdb task 06 -- duckdb-on-parquet.

Checks THREE independent things about the learner's src/lake.py, all queried
live against the Hive-partitioned Parquet lake on disk (no server involved):

  1. Completeness -- total_rows() must equal ground truth's n_observations
     (all 8 partition files present, nothing truncated).
  2. Correctness -- per_category_instock() must reproduce
     data/ground-truth.json's per_category_instock: every category's count
     exactly, avg_price within a rounding tolerance, and the category set
     must match (no missing, no extra).
  3. The pruning proof -- one_category_files(con, "electronics") must return
     EXACTLY ONE file path, and that path must belong to the
     category=electronics partition. Getting back more than one file means
     DuckDB scanned partitions it didn't need to.

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
    PARQUET_DIR,
    duckdb_connect,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)
from src.lake import (  # noqa: E402
    one_category_files,
    per_category_instock,
    total_rows,
)

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
    expected_total = gt["n_observations"]
    expected_by_cat = gt["per_category_instock"]

    con = duckdb_connect()
    try:
        # 1. Completeness.
        n = total_rows(con)
        if int(n) != expected_total:
            not_passed(f"total_rows() = {n}, expected {expected_total} exactly")

        # 2. Correctness.
        got = per_category_instock(con)
        if not got:
            not_passed("per_category_instock() returned nothing")

        missing = [cat for cat in expected_by_cat if cat not in got]
        if missing:
            not_passed(f"per_category_instock() is missing categories: {missing}")
        extra = [cat for cat in got if cat not in expected_by_cat]
        if extra:
            not_passed(f"per_category_instock() has unexpected categories: {extra}")

        for cat, exp in expected_by_cat.items():
            count, avg = got[cat]
            if int(count) != exp["count"]:
                not_passed(
                    f"per_category_instock(): category={cat!r} count={count}, "
                    f"expected {exp['count']} exactly"
                )
            if abs(float(avg) - exp["avg"]) > AVG_TOLERANCE:
                not_passed(
                    f"per_category_instock(): category={cat!r} avg_price={avg}, "
                    f"expected {exp['avg']} within {AVG_TOLERANCE}"
                )

        # 3. Partition pruning proof.
        files = list(one_category_files(con, PROBE_CATEGORY))
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
            f"total_rows={n}; {len(expected_by_cat)} categories matched ground "
            f"truth; one_category_files({PROBE_CATEGORY!r}) pruned to exactly "
            f"1 file: {only_file}"
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
