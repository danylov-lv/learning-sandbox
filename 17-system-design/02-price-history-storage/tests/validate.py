"""Validator for 02-price-history-storage. Run from the module root:

    cd 17-system-design
    uv run python 02-price-history-storage/tests/validate.py

Two independent gates, both must pass:
  1. Capacity model (src/estimate.py) -- checked numerically against an
     independent recomputation, across the committed workload.json plus
     two perturbed variants built in memory.
  2. Design doc (DESIGN.md) -- checked structurally: required sections,
     no placeholders, grounding keywords, quantitative claims, and the
     Q1..Q8 hostile-review answers.
"""

from __future__ import annotations

import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_answers,
    check_close,
    check_estimate_module,
    check_keywords,
    check_quantitative,
    check_sections,
    guarded,
    import_estimate,
    load_workload,
    not_passed,
    passed,
    read_doc,
)

DAYS_PER_YEAR = 365.25

REQUIRED_FUNCTIONS = [
    "rows_per_day",
    "rows_retained",
    "raw_bytes_retained",
    "compressed_bytes_retained",
    "change_only_rows_per_day",
    "change_only_compressed_bytes_retained",
    "hot_tier_bytes",
    "monthly_storage_cost_usd",
    "range_query_bytes_scanned",
]


# --------------------------------------------------------------------------
# Independent recomputation (never imports the learner's code)
# --------------------------------------------------------------------------

def _rows_per_day(w: dict) -> float:
    return w["tracked_products"] * w["observations_per_product_per_day"]


def _rows_retained(w: dict) -> float:
    return _rows_per_day(w) * w["retention_years"] * DAYS_PER_YEAR


def _raw_bytes_retained(w: dict) -> float:
    return _rows_retained(w) * w["avg_row_bytes"]


def _compressed_bytes_retained(w: dict) -> float:
    return _raw_bytes_retained(w) / w["compression_ratio"]


def _change_only_rows_per_day(w: dict) -> float:
    return _rows_per_day(w) * w["price_change_fraction"]


def _change_only_compressed_bytes_retained(w: dict) -> float:
    return (
        _change_only_rows_per_day(w)
        * w["retention_years"]
        * DAYS_PER_YEAR
        * w["avg_row_bytes"]
        / w["compression_ratio"]
    )


def _hot_tier_bytes(w: dict) -> float:
    return _rows_per_day(w) * w["hot_tier_days"] * w["avg_row_bytes"] / w["compression_ratio"]


def _monthly_storage_cost_usd(w: dict) -> float:
    hot = _hot_tier_bytes(w)
    cold = _compressed_bytes_retained(w) - hot
    return (hot / 1e9) * w["hot_tier_price_usd_per_gb_month"] + (cold / 1e9) * w[
        "cold_tier_price_usd_per_gb_month"
    ]


def _range_query_bytes_scanned(w: dict) -> float:
    return (
        w["observations_per_product_per_day"]
        * DAYS_PER_YEAR
        * w["avg_row_bytes"]
        / w["compression_ratio"]
        * w["good_key_scan_overhead_factor"]
    )


EXPECTED = {
    "rows_per_day": _rows_per_day,
    "rows_retained": _rows_retained,
    "raw_bytes_retained": _raw_bytes_retained,
    "compressed_bytes_retained": _compressed_bytes_retained,
    "change_only_rows_per_day": _change_only_rows_per_day,
    "change_only_compressed_bytes_retained": _change_only_compressed_bytes_retained,
    "hot_tier_bytes": _hot_tier_bytes,
    "monthly_storage_cost_usd": _monthly_storage_cost_usd,
    "range_query_bytes_scanned": _range_query_bytes_scanned,
}


def _perturb(w: dict, **overrides) -> dict:
    variant = dict(w)
    variant.update(overrides)
    return variant


def _workload_variants(base: dict) -> list:
    variant_a = _perturb(
        base,
        tracked_products=int(base["tracked_products"] * 1.7) + 13,
        observations_per_product_per_day=round(base["observations_per_product_per_day"] * 0.6 + 0.4, 4),
        price_change_fraction=round(min(base["price_change_fraction"] * 1.4, 0.5), 5),
        avg_row_bytes=base["avg_row_bytes"] + 15,
        compression_ratio=round(base["compression_ratio"] * 1.2, 3),
        retention_years=base["retention_years"] + 2,
        hot_tier_days=base["hot_tier_days"] + 45,
        hot_tier_price_usd_per_gb_month=round(base["hot_tier_price_usd_per_gb_month"] * 1.3, 5),
        cold_tier_price_usd_per_gb_month=round(base["cold_tier_price_usd_per_gb_month"] * 0.8, 6),
        good_key_scan_overhead_factor=round(base["good_key_scan_overhead_factor"] + 0.05, 3),
    )
    variant_b = _perturb(
        base,
        tracked_products=int(base["tracked_products"] * 0.42) + 7,
        observations_per_product_per_day=round(base["observations_per_product_per_day"] * 2.1 - 0.3, 4),
        price_change_fraction=round(base["price_change_fraction"] * 0.5, 5),
        avg_row_bytes=base["avg_row_bytes"] - 9,
        compression_ratio=round(base["compression_ratio"] * 0.75, 3),
        retention_years=base["retention_years"] + 1,
        hot_tier_days=max(base["hot_tier_days"] - 30, 5),
        hot_tier_price_usd_per_gb_month=round(base["hot_tier_price_usd_per_gb_month"] * 0.85, 5),
        cold_tier_price_usd_per_gb_month=round(base["cold_tier_price_usd_per_gb_month"] * 1.6, 6),
        good_key_scan_overhead_factor=round(base["good_key_scan_overhead_factor"] * 0.9, 3),
    )
    return [base, variant_a, variant_b]


# --------------------------------------------------------------------------
# Design doc gate
# --------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "Requirements and access patterns",
    "Physical layout",
    "Write path",
    "Read paths",
    "Capacity model",
    "Retention and tiering",
    "Bottlenecks and failure modes",
    "Evolution at 10x",
    "Hostile review responses",
]

MIN_CHARS = {
    "Requirements and access patterns": 300,
    "Physical layout": 400,
    "Write path": 300,
    "Read paths": 400,
    "Capacity model": 400,
    "Retention and tiering": 300,
    "Bottlenecks and failure modes": 300,
    "Evolution at 10x": 250,
    "Hostile review responses": 1600,
    "_default": 250,
}

KEYWORDS = [
    "partition",
    "partitioning",
    "ordering key",
    "clustering key",
    "sort key",
    "sorting key",
    "compression",
    "columnar",
    "encoding",
    "retention",
    "hot tier",
    "cold tier",
    "tiering",
    "compaction",
    "backfill",
    "change-only",
    "delta",
    "fill-forward",
    "granule",
    "row group",
    "cardinality",
    "write amplification",
    "ttl",
    "snapshot",
    "late-arriving",
    "dedup",
    "pruning",
]

QUESTION_IDS = [f"Q{i}" for i in range(1, 9)]


@guarded
def main() -> None:
    workload_path = TASK_DIR / "workload.json"
    base_workload = load_workload(workload_path)

    module = import_estimate(TASK_DIR)
    check_estimate_module(module, REQUIRED_FUNCTIONS)

    variants = _workload_variants(base_workload)

    for fn_name in REQUIRED_FUNCTIONS:
        fn = getattr(module, fn_name)
        expected_fn = EXPECTED[fn_name]
        for i, variant in enumerate(variants):
            try:
                actual = fn(variant)
            except NotImplementedError:
                not_passed(f"{fn_name}: not implemented (raises NotImplementedError)")
            except Exception as e:  # noqa: BLE001
                not_passed(f"{fn_name}: raised {type(e).__name__}: {e} on workload variant {i}")
            expected = expected_fn(variant)
            check_close(actual, expected, label=f"{fn_name} (variant {i})")

    design_path = TASK_DIR / "DESIGN.md"
    sections = check_sections(design_path, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = read_doc(design_path)
    check_keywords(full_text, KEYWORDS, min_hits=10, label="DESIGN.md grounding vocabulary")
    check_quantitative(full_text, min_numbers=20, label="DESIGN.md")

    check_answers(
        design_path,
        QUESTION_IDS,
        min_answered=8,
        min_chars=220,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )

    passed("capacity model checked on 3 workload variants; design doc structure OK")


if __name__ == "__main__":
    main()
