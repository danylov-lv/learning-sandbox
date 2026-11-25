"""Validator for 03-row-groups-and-pushdown.

Run from the module root:
    uv run python 03-row-groups-and-pushdown/tests/validate.py
"""

import sys
from pathlib import Path

import pyarrow.parquet as pq

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    approx,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_results,
    passed,
)

VARIANTS = [
    "rg8k-unsorted", "rg128k-unsorted", "rg1m-unsorted",
    "rg8k-sorted", "rg128k-sorted", "rg1m-sorted",
]
OUT_DIR = DATA_DIR / "rowgroups"
RESULTS_PATH = TASK_ROOT / "results-local.json"

# Structural pruning targets, measured on the reference implementation against
# the current dataset with a ~2x safety margin. If you regenerate the dataset
# at a very different size these ratios should still hold (row-group pruning
# depends on the sort order and row-group size, not on absolute row count),
# but if this task starts failing after a large `--gb` change, re-measure and
# adjust the thresholds below together with the README.
RG8K_SORTED_MAX_RATIO = 0.05
RG8K_UNSORTED_MIN_RATIO = 0.5
RG128K_SORTED_MAX_RATIO = 0.15
RG128K_UNSORTED_MIN_RATIO = 0.5

ROW_GROUP_COUNT_FACTOR = 10  # rg8k must have at least this many times more row groups than rg1m


@guarded
def main():
    gt = load_ground_truth()
    total_rows = gt["total_rows"]
    fp = gt["filter_probe"]

    row_group_counts = {}
    for variant in VARIANTS:
        path = OUT_DIR / f"snapshots-{variant}.parquet"
        if not path.exists():
            fail(f"missing output file {path} — run tests/bench.py first")

        pf = pq.ParquetFile(path)
        meta = pf.metadata
        if meta.num_rows != total_rows:
            fail(f"{variant}: num_rows={meta.num_rows}, expected {total_rows} (from ground-truth.json)")
        row_group_counts[variant] = meta.num_row_groups

    # row-group count sanity: rg8k should have far more, smaller row groups than rg1m
    for suffix in ("unsorted", "sorted"):
        rg8k = row_group_counts[f"rg8k-{suffix}"]
        rg1m = row_group_counts[f"rg1m-{suffix}"]
        if rg1m == 0 or rg8k < ROW_GROUP_COUNT_FACTOR * rg1m:
            fail(
                f"rg8k-{suffix} has {rg8k} row groups, rg1m-{suffix} has {rg1m} — "
                f"expected rg8k to have at least {ROW_GROUP_COUNT_FACTOR}x more "
                f"(did row_group_size actually take effect per variant?)"
            )

    results = load_results(RESULTS_PATH, what="results-local.json")
    variants_results = results.get("variants", {})

    for variant in VARIANTS:
        v = variants_results.get(variant)
        if v is None:
            fail(f"results-local.json missing measurements for variant '{variant}'")
        for key in ("matching_row_groups", "total_row_groups", "probe_time", "probe_rows", "probe_price_sum"):
            if key not in v:
                fail(f"results-local.json variant '{variant}' missing '{key}'")

        approx(v["probe_rows"], fp["rows"], rel_tol=1e-6, what=f"{variant}: probe_rows")
        approx(v["probe_price_sum"], fp["price_sum"], rel_tol=1e-6, what=f"{variant}: probe_price_sum")

    def ratio(variant):
        v = variants_results[variant]
        total = v["total_row_groups"]
        if total == 0:
            fail(f"{variant}: total_row_groups is 0")
        return v["matching_row_groups"] / total

    r_8k_sorted = ratio("rg8k-sorted")
    r_8k_unsorted = ratio("rg8k-unsorted")
    r_128k_sorted = ratio("rg128k-sorted")
    r_128k_unsorted = ratio("rg128k-unsorted")

    if r_8k_sorted > RG8K_SORTED_MAX_RATIO:
        fail(
            f"rg8k-sorted: {r_8k_sorted:.3f} of row groups matched the probe, "
            f"expected <= {RG8K_SORTED_MAX_RATIO} — sorting by (source_id, captured_at) "
            f"should make most row groups provably irrelevant to the probe"
        )
    if r_8k_unsorted < RG8K_UNSORTED_MIN_RATIO:
        fail(
            f"rg8k-unsorted: only {r_8k_unsorted:.3f} of row groups matched the probe, "
            f"expected >= {RG8K_UNSORTED_MIN_RATIO} — unsorted row groups should span the "
            f"whole source/time range, so almost none should be prunable"
        )
    if r_128k_sorted > RG128K_SORTED_MAX_RATIO:
        fail(
            f"rg128k-sorted: {r_128k_sorted:.3f} of row groups matched the probe, "
            f"expected <= {RG128K_SORTED_MAX_RATIO}"
        )
    if r_128k_unsorted < RG128K_UNSORTED_MIN_RATIO:
        fail(
            f"rg128k-unsorted: only {r_128k_unsorted:.3f} of row groups matched the probe, "
            f"expected >= {RG128K_UNSORTED_MIN_RATIO}"
        )

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        f"row-group pruning ratios: rg8k sorted={r_8k_sorted:.3f} unsorted={r_8k_unsorted:.3f}, "
        f"rg128k sorted={r_128k_sorted:.3f} unsorted={r_128k_unsorted:.3f}"
    )


if __name__ == "__main__":
    main()
