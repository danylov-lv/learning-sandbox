"""Benchmark harness for 03-row-groups-and-pushdown.

Imports the learner's write_rowgroups.write_all, runs it once (it writes all
six variants), then for each variant runs the probe query two ways:

    (a) predicate pushdown via pyarrow.dataset, measuring wall time;
    (b) row-group-statistics analysis: for each row group, read min/max
        statistics for source_id and captured_at from Parquet footer
        metadata and count how many row groups COULD contain a matching row
        (i.e. their stat range overlaps the probe range) vs how many exist
        in total. This never reads a single data page — it is pure metadata
        inspection, which is the whole point: row-group stats let you know
        what to skip without decompressing it.

Probe query (mirrors data/ground-truth.json's filter_probe exactly):

    source_id == filter_probe.source_id
    AND captured_at >= filter_probe.captured_at_from 00:00:00Z
    AND captured_at <  (filter_probe.captured_at_to + 1 day) 00:00:00Z

i.e. captured_at_to is an inclusive whole day (through 23:59:59.999999Z),
expressed as a half-open interval on the next day's midnight to avoid any
microsecond-boundary ambiguity — this is exactly how generate.py computed
the ground-truth probe aggregate.

Writes 03-row-groups-and-pushdown/results-local.json and prints a table.

Run from the module root:
    uv run python 03-row-groups-and-pushdown/tests/bench.py
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import DATA_DIR, RAW_DIR, fail, guarded, load_ground_truth, load_learner_module  # noqa: E402

VARIANTS = [
    "rg8k-unsorted", "rg128k-unsorted", "rg1m-unsorted",
    "rg8k-sorted", "rg128k-sorted", "rg1m-sorted",
]
OUT_DIR = DATA_DIR / "rowgroups"
RESULTS_PATH = TASK_ROOT / "results-local.json"


def probe_bounds(gt):
    fp = gt["filter_probe"]
    from_dt = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    return fp["source_id"], from_dt, to_dt


def rowgroup_overlap_count(path, source_id, from_dt, to_dt):
    pf = pq.ParquetFile(path)
    meta = pf.metadata
    names = pf.schema_arrow.names
    src_idx = names.index("source_id")
    ts_idx = names.index("captured_at")

    total = meta.num_row_groups
    matching = 0
    for i in range(total):
        rg = meta.row_group(i)
        src_stats = rg.column(src_idx).statistics
        ts_stats = rg.column(ts_idx).statistics
        if src_stats is None or ts_stats is None or not src_stats.has_min_max or not ts_stats.has_min_max:
            matching += 1  # can't prune without stats — conservatively assume it matches
            continue
        source_ok = src_stats.min <= source_id <= src_stats.max
        ts_ok = ts_stats.min < to_dt and ts_stats.max >= from_dt
        if source_ok and ts_ok:
            matching += 1
    return matching, total


@guarded
def main():
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_DIR} — run `uv run python generate.py` from the module root first")

    gt = load_ground_truth()
    source_id, from_dt, to_dt = probe_bounds(gt)

    mod = load_learner_module(TASK_ROOT / "src" / "write_rowgroups.py", "write_rowgroups")
    if not hasattr(mod, "write_all"):
        fail("src/write_rowgroups.py has no write_all(raw_dir, out_dir) function")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"writing all variants to {OUT_DIR} ...")
    t0 = time.perf_counter()
    rows_written = mod.write_all(RAW_DIR, OUT_DIR)
    write_total_s = time.perf_counter() - t0
    print(f"write_all done in {write_total_s:.1f}s")

    if not isinstance(rows_written, dict):
        fail(f"write_all must return a dict of {{variant: rows_written}}, got {type(rows_written).__name__}")

    results = {"write_total_s": write_total_s, "variants": {}}

    header = f"{'variant':<20}{'rg_match':>10}{'rg_total':>10}{'ratio':>8}{'probe_s':>10}{'rows':>8}"
    print(header)
    for variant in VARIANTS:
        path = OUT_DIR / f"snapshots-{variant}.parquet"
        if not path.exists():
            fail(f"expected output file missing: {path}")
        if variant not in rows_written:
            fail(f"write_all did not report a row count for variant '{variant}'")

        matching, total = rowgroup_overlap_count(path, source_id, from_dt, to_dt)

        dataset = ds.dataset(path, format="parquet")
        filt = (
            (ds.field("source_id") == source_id)
            & (ds.field("captured_at") >= from_dt)
            & (ds.field("captured_at") < to_dt)
        )
        t0 = time.perf_counter()
        table = dataset.to_table(filter=filt)
        probe_time = time.perf_counter() - t0

        probe_rows = table.num_rows
        price_col = table.column("price")
        probe_price_sum = float(sum(v.as_py() for v in price_col if v.is_valid))

        results["variants"][variant] = {
            "matching_row_groups": matching,
            "total_row_groups": total,
            "probe_time": probe_time,
            "probe_rows": probe_rows,
            "probe_price_sum": probe_price_sum,
        }
        ratio = matching / total if total else 0.0
        print(f"{variant:<20}{matching:>10}{total:>10}{ratio:>8.2f}{probe_time:>10.4f}{probe_rows:>8}")

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
