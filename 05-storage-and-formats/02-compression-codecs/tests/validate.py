"""Validator for 02-compression-codecs.

Run from the module root:
    uv run python 02-compression-codecs/tests/validate.py
"""

import sys
from pathlib import Path

import pyarrow.parquet as pq

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    DATA_DIR,
    check_notes_filled,
    fail,
    guarded,
    load_ground_truth,
    load_results,
    passed,
)

VARIANTS = ["none", "snappy", "gzip", "zstd3", "zstd19"]
OUT_DIR = DATA_DIR / "codecs"
RESULTS_PATH = TASK_ROOT / "results-local.json"

EXPECTED_CODEC = {
    "none": "UNCOMPRESSED",
    "snappy": "SNAPPY",
    "gzip": "GZIP",
    "zstd3": "ZSTD",
    "zstd19": "ZSTD",
}

# require strict size ordering only when files differ by more than this margin,
# so near-ties (e.g. two zstd levels on already-dense data) don't flip-flop
SIZE_TOLERANCE = 0.02


@guarded
def main():
    gt = load_ground_truth()
    total_rows = gt["total_rows"]

    metas = {}
    sizes = {}
    for variant in VARIANTS:
        path = OUT_DIR / f"snapshots-{variant}.parquet"
        if not path.exists():
            fail(f"missing output file {path} — run tests/bench.py first")

        pf = pq.ParquetFile(path)
        meta = pf.metadata
        metas[variant] = meta
        sizes[variant] = path.stat().st_size

        if meta.num_rows != total_rows:
            fail(f"{variant}: num_rows={meta.num_rows}, expected {total_rows} (from ground-truth.json)")

        names = pf.schema_arrow.names
        if "price" not in names:
            fail(f"{variant}: schema has no 'price' column — got {names}")
        price_idx = names.index("price")

        rg0 = meta.row_group(0)
        actual_codec = rg0.column(price_idx).compression
        expected_codec = EXPECTED_CODEC[variant]
        if actual_codec != expected_codec:
            fail(
                f"{variant}: price column compression is {actual_codec!r}, "
                f"expected {expected_codec!r} — did you pass the right compression kwarg?"
            )

    def bigger(a, b):
        """True if size[a] is meaningfully bigger than size[b] (beyond tolerance)."""
        if sizes[b] == 0:
            return sizes[a] > sizes[b]
        return (sizes[a] - sizes[b]) / sizes[b] > SIZE_TOLERANCE

    if not bigger("none", "snappy"):
        fail(
            f"expected none ({sizes['none']} B) to be meaningfully bigger than "
            f"snappy ({sizes['snappy']} B) — uncompressed should not be the smallest"
        )
    if not bigger("snappy", "zstd3"):
        fail(
            f"expected snappy ({sizes['snappy']} B) to be meaningfully bigger than "
            f"zstd3 ({sizes['zstd3']} B) — zstd should out-compress snappy at equal-ish speed tiers"
        )
    if not bigger("gzip", "zstd19"):
        fail(
            f"expected gzip ({sizes['gzip']} B) to be meaningfully bigger than "
            f"zstd19 ({sizes['zstd19']} B) — zstd at a high level should beat gzip"
        )

    results = load_results(RESULTS_PATH, what="results-local.json")
    if "write_total_s" not in results:
        fail("results-local.json missing 'write_total_s' — run tests/bench.py, do not hand-edit it")
    variants_results = results.get("variants", {})
    for variant in VARIANTS:
        v = variants_results.get(variant)
        if v is None:
            fail(f"results-local.json missing measurements for variant '{variant}'")
        for key in ("rows_written", "file_size_bytes", "read_time_s"):
            if key not in v:
                fail(f"results-local.json variant '{variant}' missing '{key}'")
        if v["rows_written"] != total_rows:
            fail(f"results-local.json: variant '{variant}' rows_written={v['rows_written']}, expected {total_rows}")

    check_notes_filled(TASK_ROOT / "NOTES.md")

    passed(
        "all five variants correct rows, codecs match, size ordering holds "
        f"(none={sizes['none']}, snappy={sizes['snappy']}, gzip={sizes['gzip']}, "
        f"zstd3={sizes['zstd3']}, zstd19={sizes['zstd19']})"
    )


if __name__ == "__main__":
    main()
