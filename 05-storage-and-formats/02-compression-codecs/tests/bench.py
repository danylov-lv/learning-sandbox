"""Benchmark harness for 02-compression-codecs.

Imports the learner's write_codecs.write_all, runs it once (it writes all
five variants), then measures on-disk size and full-scan read time for each
variant. Writes results-local.json next to this task's README and prints a
summary table.

Run from the module root:
    uv run python 02-compression-codecs/tests/bench.py
"""

import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import DATA_DIR, RAW_DIR, fail, guarded, load_learner_module  # noqa: E402

VARIANTS = ["none", "snappy", "gzip", "zstd3", "zstd19"]
OUT_DIR = DATA_DIR / "codecs"
RESULTS_PATH = TASK_ROOT / "results-local.json"


@guarded
def main():
    if not RAW_DIR.exists() or not any(RAW_DIR.glob("*.jsonl")):
        fail(f"no raw data at {RAW_DIR} — run `uv run python generate.py` from the module root first")

    mod = load_learner_module(TASK_ROOT / "src" / "write_codecs.py", "write_codecs")
    if not hasattr(mod, "write_all"):
        fail("src/write_codecs.py has no write_all(raw_dir, out_dir) function")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"writing all variants to {OUT_DIR} ...")
    t0 = time.perf_counter()
    rows_written = mod.write_all(RAW_DIR, OUT_DIR)
    write_total_s = time.perf_counter() - t0

    if not isinstance(rows_written, dict):
        fail(f"write_all must return a dict of {{variant: rows_written}}, got {type(rows_written).__name__}")

    results = {"write_total_s": write_total_s, "variants": {}}

    print(f"{'variant':<10}{'rows':>10}{'size_mb':>12}{'read_s':>10}")
    for variant in VARIANTS:
        path = OUT_DIR / f"snapshots-{variant}.parquet"
        if not path.exists():
            fail(f"expected output file missing: {path}")
        if variant not in rows_written:
            fail(f"write_all did not report a row count for variant '{variant}'")

        size_bytes = path.stat().st_size

        t0 = time.perf_counter()
        table = pq.read_table(path)
        read_time_s = time.perf_counter() - t0

        results["variants"][variant] = {
            "rows_written": rows_written[variant],
            "file_size_bytes": size_bytes,
            "read_time_s": read_time_s,
        }
        print(f"{variant:<10}{table.num_rows:>10}{size_bytes / 1e6:>12.1f}{read_time_s:>10.2f}")

    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS_PATH}")
    print(f"write_all total time: {write_total_s:.1f}s")


if __name__ == "__main__":
    main()
