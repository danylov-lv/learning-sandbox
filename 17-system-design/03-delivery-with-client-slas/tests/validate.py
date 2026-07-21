"""Validator for 03-delivery-with-client-slas.

Run from the module root:
    cd 17-system-design
    uv run python 03-delivery-with-client-slas/tests/validate.py

Two independent gates, both must pass:
  1. Capacity model (src/estimate.py) -- checked numerically against an
     independent recomputation, across the committed workload.json plus
     perturbed in-memory variants.
  2. Design doc (DESIGN.md) -- checked structurally: required sections,
     grounding keywords, quantitative content, and genuinely answered
     hostile-review questions.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
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
)

WORKLOAD_PATH = TASK_DIR / "workload.json"
DESIGN_PATH = TASK_DIR / "DESIGN.md"

MINUTES_PER_MONTH = 30 * 24 * 60  # pinned 30-day month, see README

REQUIRED_FUNCTIONS = [
    "records_per_day_total",
    "average_delivery_rps",
    "peak_delivery_rps",
    "error_budget_minutes_per_month",
    "deliveries_per_day",
    "backlog_after_outage",
    "drain_seconds_after_outage",
    "freshness_breach_count",
    "monthly_penalty_usd",
]

REQUIRED_SECTIONS = [
    "Requirements and SLA/SLO definitions",
    "Architecture",
    "Contracts and schemas",
    "Prioritization under a shared budget",
    "Delivery, retry and replay",
    "Capacity model",
    "Breach detection and reporting",
    "Bottlenecks and failure modes",
    "Evolution at 10x",
    "Hostile Review",
]

MIN_CHARS = {
    "Requirements and SLA/SLO definitions": 500,
    "Architecture": 500,
    "Contracts and schemas": 400,
    "Prioritization under a shared budget": 400,
    "Delivery, retry and replay": 400,
    "Capacity model": 400,
    "Breach detection and reporting": 400,
    "Bottlenecks and failure modes": 400,
    "Evolution at 10x": 300,
    "Hostile Review": 600,
    "_default": 300,
}

GROUNDING_KEYWORDS = [
    "SLA",
    "SLO",
    "error budget",
    "freshness",
    "availability",
    "backpressure",
    "starvation",
    "priority",
    "retry",
    "idempotent",
    "replay",
    "backlog",
    "breach",
    "penalty",
    "dead letter",
    "webhook",
]
MIN_GROUNDING_HITS = 8
MIN_QUANTITATIVE = 6

QUESTION_IDS = [f"Q{i}" for i in range(1, 9)]
MIN_ANSWERED = 8
MIN_ANSWER_CHARS = 200


# --------------------------------------------------------------------------
# Gate 1: independent recomputation of the capacity model
# --------------------------------------------------------------------------

def _records_per_day_total(w: dict) -> float:
    return float(sum(t["client_count"] * t["records_per_client_per_day"] for t in w["tiers"].values()))


def _average_delivery_rps(w: dict) -> float:
    return _records_per_day_total(w) / 86400.0


def _peak_delivery_rps(w: dict) -> float:
    return _average_delivery_rps(w) * w["peak_hour_concentration_factor"]


def _error_budget_minutes_per_month(w: dict, tier: str) -> float:
    pct = w["tiers"][tier]["monthly_availability_target_pct"]
    return (100.0 - pct) / 100.0 * MINUTES_PER_MONTH


def _deliveries_per_day(w: dict, tier: str) -> float:
    t = w["tiers"][tier]
    return (t["client_count"] * t["records_per_client_per_day"]) / t["delivery_batch_size"]


def _backlog_after_outage(w: dict) -> float:
    return _average_delivery_rps(w) * w["outage_minutes"] * 60.0


def _drain_seconds_after_outage(w: dict) -> float:
    capacity = w["total_pipeline_drain_capacity_rps"]
    avg = _average_delivery_rps(w)
    net_rate = capacity - avg
    if net_rate <= 0:
        not_passed("workload fixture invalid: drain capacity does not exceed average delivery rate")
    return _backlog_after_outage(w) / net_rate


def _total_recovery_minutes(w: dict) -> float:
    return w["outage_minutes"] + _drain_seconds_after_outage(w) / 60.0


def _freshness_breach_count(w: dict) -> int:
    total_minutes = _total_recovery_minutes(w)
    return sum(1 for t in w["tiers"].values() if t["freshness_deadline_minutes"] < total_minutes)


def _monthly_penalty_usd(w: dict) -> float:
    return sum(
        w["observed_breaches"][name] * tier["penalty_usd_per_breach"]
        for name, tier in w["tiers"].items()
    )


def _perturbed_variants(base: dict) -> list[dict]:
    """Build at least 2 in-memory perturbed workloads, distinct enough that
    a hardcoded return value (correct only on `base`) will diverge."""
    variant_a = copy.deepcopy(base)
    for name, mult in (("gold", 2), ("silver", 2), ("bronze", 2)):
        variant_a["tiers"][name]["client_count"] *= mult
    variant_a["tiers"]["gold"]["monthly_availability_target_pct"] = 99.9
    variant_a["tiers"]["silver"]["monthly_availability_target_pct"] = 99.5
    variant_a["tiers"]["bronze"]["monthly_availability_target_pct"] = 97.5
    variant_a["peak_hour_concentration_factor"] = 3.0
    variant_a["outage_minutes"] = 45
    variant_a["total_pipeline_drain_capacity_rps"] = 500
    variant_a["observed_breaches"] = {"gold": 2, "silver": 9, "bronze": 40}

    variant_b = copy.deepcopy(base)
    variant_b["tiers"]["gold"]["client_count"] = 10
    variant_b["tiers"]["gold"]["records_per_client_per_day"] = 25000
    variant_b["tiers"]["gold"]["delivery_batch_size"] = 250
    variant_b["tiers"]["silver"]["client_count"] = 80
    variant_b["tiers"]["silver"]["records_per_client_per_day"] = 10000
    variant_b["tiers"]["silver"]["freshness_deadline_minutes"] = 30
    variant_b["tiers"]["bronze"]["client_count"] = 900
    variant_b["tiers"]["bronze"]["records_per_client_per_day"] = 2500
    variant_b["tiers"]["bronze"]["monthly_availability_target_pct"] = 95.0
    variant_b["peak_hour_concentration_factor"] = 5.0
    variant_b["outage_minutes"] = 180
    variant_b["total_pipeline_drain_capacity_rps"] = 150
    variant_b["observed_breaches"] = {"gold": 1, "silver": 3, "bronze": 5}

    return [variant_a, variant_b]


def _check_capacity_model(task_dir: Path) -> None:
    module = import_estimate(task_dir)
    check_estimate_module(module, REQUIRED_FUNCTIONS)

    base = load_workload(WORKLOAD_PATH)
    workloads = [("workload.json", base)] + [
        (f"perturbed variant {i + 1}", w) for i, w in enumerate(_perturbed_variants(base))
    ]

    for label, w in workloads:
        check_close(
            module.records_per_day_total(w),
            _records_per_day_total(w),
            label=f"records_per_day_total [{label}]",
        )
        check_close(
            module.average_delivery_rps(w),
            _average_delivery_rps(w),
            label=f"average_delivery_rps [{label}]",
        )
        check_close(
            module.peak_delivery_rps(w),
            _peak_delivery_rps(w),
            label=f"peak_delivery_rps [{label}]",
        )
        check_close(
            module.backlog_after_outage(w),
            _backlog_after_outage(w),
            label=f"backlog_after_outage [{label}]",
        )
        check_close(
            module.drain_seconds_after_outage(w),
            _drain_seconds_after_outage(w),
            label=f"drain_seconds_after_outage [{label}]",
        )
        check_close(
            module.freshness_breach_count(w),
            _freshness_breach_count(w),
            rel_tol=1e-9,
            label=f"freshness_breach_count [{label}]",
        )
        check_close(
            module.monthly_penalty_usd(w),
            _monthly_penalty_usd(w),
            label=f"monthly_penalty_usd [{label}]",
        )
        for tier in ("gold", "silver", "bronze"):
            check_close(
                module.error_budget_minutes_per_month(w, tier),
                _error_budget_minutes_per_month(w, tier),
                label=f"error_budget_minutes_per_month[{tier}] [{label}]",
            )
            check_close(
                module.deliveries_per_day(w, tier),
                _deliveries_per_day(w, tier),
                label=f"deliveries_per_day[{tier}] [{label}]",
            )


# --------------------------------------------------------------------------
# Gate 2: design doc structure
# --------------------------------------------------------------------------

def _check_design_doc() -> None:
    sections = check_sections(DESIGN_PATH, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = "\n".join(sections.values())
    check_keywords(full_text, GROUNDING_KEYWORDS, MIN_GROUNDING_HITS, label="DESIGN.md")
    check_quantitative(full_text, MIN_QUANTITATIVE, label="DESIGN.md")

    check_answers(
        DESIGN_PATH,
        QUESTION_IDS,
        MIN_ANSWERED,
        min_chars=MIN_ANSWER_CHARS,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )


@guarded
def main() -> None:
    _check_capacity_model(TASK_DIR)
    _check_design_doc()
    passed("capacity model matches independent recomputation across 3 workloads; DESIGN.md structurally complete")


if __name__ == "__main__":
    main()
