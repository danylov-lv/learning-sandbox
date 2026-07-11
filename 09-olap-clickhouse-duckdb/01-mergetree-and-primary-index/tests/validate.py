"""Validator for 09-olap-clickhouse-duckdb task 01 -- mergetree-and-primary-index.

Checks TWO independent things about the learner's src/queries.py:

  1. Correctness -- category_instock_agg() must reproduce
     data/ground-truth.json's per_category_instock exactly (count) and
     within a rounding tolerance (avg_price).
  2. The pruning proof -- pruned_sum() must read far fewer rows off disk
     (harness.ch_read_rows) than full_scan_sum(), and one_product_history()
     for a single real product must read far fewer rows still. This is the
     structural evidence that the MergeTree ORDER BY acts as a sparse
     primary index and lets ClickHouse skip granules.

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
    ch_client,
    ch_query,
    ch_read_rows,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)
from src.queries import (  # noqa: E402
    category_instock_agg,
    full_scan_sum,
    one_product_history,
    pruned_sum,
)

AVG_TOLERANCE = 0.01
PRUNE_MAX_PRODUCT_ID = 50
# The pruned read must be a small fraction of the full-scan read to count
# as proof of pruning, not just "somewhat less".
PRUNE_FRACTION = 0.10


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["per_category_instock"]
    total_rows = gt["row_counts"]["observations"]

    client = ch_client()
    try:
        # 1. Correctness: category_instock_agg() vs ground truth.
        rows = ch_query(category_instock_agg(), client=client)
        if not rows:
            not_passed("category_instock_agg() returned no rows")

        got = {r[0]: (r[1], r[2]) for r in rows}

        missing = [cat for cat in expected if cat not in got]
        if missing:
            not_passed(f"category_instock_agg() is missing categories: {missing}")

        for cat, (exp_count, exp_avg) in (
            (c, (v["count"], v["avg"])) for c, v in expected.items()
        ):
            count, avg = got[cat]
            if int(count) != exp_count:
                not_passed(
                    f"category_instock_agg(): category={cat!r} count={count}, "
                    f"expected {exp_count} exactly"
                )
            if abs(float(avg) - exp_avg) > AVG_TOLERANCE:
                not_passed(
                    f"category_instock_agg(): category={cat!r} avg={avg}, "
                    f"expected {exp_avg} within {AVG_TOLERANCE}"
                )

        # 2. Pruning proof: full scan vs an ORDER-BY-prefix-aligned filter.
        full_reads = ch_read_rows(full_scan_sum(), client=client)
        if full_reads < total_rows * 0.9:
            not_passed(
                f"full_scan_sum() read only {full_reads} rows out of {total_rows} -- "
                "expected it to read (close to) the whole table; check it has no "
                "prunable WHERE clause"
            )

        pruned_reads = ch_read_rows(
            pruned_sum("electronics", PRUNE_MAX_PRODUCT_ID), client=client
        )
        if pruned_reads >= full_reads:
            not_passed(
                f"pruned_sum() read {pruned_reads} rows, full_scan_sum() read "
                f"{full_reads} -- pruned read did not beat the full scan"
            )
        if pruned_reads >= total_rows * PRUNE_FRACTION:
            not_passed(
                f"pruned_sum() read {pruned_reads} rows out of {total_rows} total "
                f"({pruned_reads / total_rows:.1%}) -- expected under "
                f"{PRUNE_FRACTION:.0%}; check the WHERE clause aligns with "
                "ORDER BY (category, product_id, scraped_at)"
            )

        # 3. one_product_history() for a real (category, product_id) pair
        #    must prune at least as hard as pruned_sum, since it constrains
        #    two leading-prefix columns with equality instead of one
        #    equality + one range.
        sample = ch_query(
            "SELECT category, product_id FROM observations_raw "
            "WHERE category = 'electronics' LIMIT 1",
            client=client,
        )
        if not sample:
            not_passed("could not find a sample (category, product_id) row to probe")
        sample_category, sample_product_id = sample[0]

        history_rows = ch_query(
            one_product_history(sample_category, int(sample_product_id)), client=client
        )
        if not history_rows:
            not_passed(
                f"one_product_history({sample_category!r}, {sample_product_id}) "
                "returned no rows for a product known to exist"
            )
        if len(history_rows[0]) != 2:
            not_passed(
                "one_product_history() must select exactly two columns "
                "(scraped_at, price)"
            )

        history_reads = ch_read_rows(
            one_product_history(sample_category, int(sample_product_id)), client=client
        )
        if history_reads >= full_reads:
            not_passed(
                f"one_product_history() read {history_reads} rows, full scan read "
                f"{full_reads} -- expected far fewer (single-product lookup should "
                "prune hard on category + product_id)"
            )

        passed(
            f"correctness OK for {len(expected)} categories; pruning proven: "
            f"full_scan={full_reads} rows, pruned_sum={pruned_reads} rows "
            f"({pruned_reads / total_rows:.2%} of {total_rows}), "
            f"one_product_history={history_reads} rows"
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
