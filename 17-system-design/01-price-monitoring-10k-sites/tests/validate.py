"""Validator for 01-price-monitoring-10k-sites.

Run from the module root:

    cd 17-system-design
    uv run python 01-price-monitoring-10k-sites/tests/validate.py

Gate 1 (capacity model): calls every required function in src/estimate.py
against the committed workload.json plus two perturbed variants built here
in memory, and compares against this file's own independent recomputation
of the same pinned formula (see the task README's "Capacity model
contract"). Gate 2 (design doc): structural checks on DESIGN.md.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    guarded,
    passed,
    not_passed,
    load_workload,
    check_close,
    import_estimate,
    check_estimate_module,
    check_sections,
    check_keywords,
    check_quantitative,
    check_answers,
)

REQUIRED_FUNCS = [
    "daily_fetch_attempts",
    "average_fetches_per_second",
    "peak_fetches_per_second",
    "required_concurrency",
    "pod_count",
    "egress_bytes_per_day",
    "monthly_proxy_cost_usd",
]

MIN_PER_DAY = 1440.0
SEC_PER_DAY = 86400.0
BYTES_PER_GB = 1_000_000_000.0
DAYS_PER_MONTH = 30.0


# --------------------------------------------------------------------------
# Independent recomputation of the pinned formula (see README)
# --------------------------------------------------------------------------

def _ref_daily_scheduled_checks(w: dict) -> float:
    total = w["total_tracked_urls"]
    checks = 0.0
    for tier in w["tiers"].values():
        cycles_per_day = MIN_PER_DAY / tier["refresh_interval_minutes"]
        checks += total * tier["fraction"] * cycles_per_day
    return checks


def _ref_expected_attempts_per_check(w: dict) -> float:
    p = w["success_rate_first_attempt"]
    n = w["max_attempts"]
    return sum((1.0 - p) ** i for i in range(n))


def _ref_daily_fetch_attempts(w: dict) -> float:
    return _ref_daily_scheduled_checks(w) * _ref_expected_attempts_per_check(w)


def _ref_average_fps(w: dict) -> float:
    return _ref_daily_fetch_attempts(w) / SEC_PER_DAY


def _ref_peak_fps(w: dict) -> float:
    return _ref_average_fps(w) * w["peak_hour_factor"]


def _ref_required_concurrency(w: dict) -> float:
    little = _ref_peak_fps(w) * (w["avg_fetch_latency_ms"] / 1000.0)
    return little / w["target_utilization"]


def _ref_pod_count(w: dict) -> int:
    return math.ceil(_ref_required_concurrency(w) / w["worker_concurrency_per_pod"])


def _ref_egress_bytes_per_day(w: dict) -> float:
    return _ref_daily_fetch_attempts(w) * w["avg_response_size_bytes"]


def _ref_monthly_proxy_cost(w: dict) -> float:
    return _ref_egress_bytes_per_day(w) * DAYS_PER_MONTH / BYTES_PER_GB * w["proxy_cost_usd_per_gb"]


REF_FUNCS = {
    "daily_fetch_attempts": _ref_daily_fetch_attempts,
    "average_fetches_per_second": _ref_average_fps,
    "peak_fetches_per_second": _ref_peak_fps,
    "required_concurrency": _ref_required_concurrency,
    "pod_count": _ref_pod_count,
    "egress_bytes_per_day": _ref_egress_bytes_per_day,
    "monthly_proxy_cost_usd": _ref_monthly_proxy_cost,
}


def _variants(base: dict) -> list:
    v1 = copy.deepcopy(base)
    v1["total_tracked_urls"] = int(base["total_tracked_urls"] * 1.37) + 191
    v1["success_rate_first_attempt"] = 0.842
    v1["max_attempts"] = 3
    v1["peak_hour_factor"] = 1.9
    v1["avg_fetch_latency_ms"] = 412
    v1["target_utilization"] = 0.8

    v2 = copy.deepcopy(base)
    v2["tiers"] = {
        "hot": {"fraction": 0.114, "refresh_interval_minutes": 10},
        "warm": {"fraction": 0.276, "refresh_interval_minutes": 180},
        "cold": {"fraction": 0.610, "refresh_interval_minutes": 2880},
    }
    v2["avg_response_size_bytes"] = 152300
    v2["worker_concurrency_per_pod"] = 64
    v2["proxy_cost_usd_per_gb"] = 2.10
    v2["success_rate_first_attempt"] = 0.777
    v2["max_attempts"] = 5

    return [base, v1, v2]


@guarded
def main() -> None:
    workload_path = TASK_DIR / "workload.json"
    base = load_workload(workload_path)

    module = import_estimate(TASK_DIR)
    check_estimate_module(module, REQUIRED_FUNCS)

    for idx, variant in enumerate(_variants(base)):
        for name in REQUIRED_FUNCS:
            fn = getattr(module, name)
            try:
                actual = fn(variant)
            except NotImplementedError:
                not_passed(f"src/estimate.py: {name} is not implemented")
            except Exception as e:  # noqa: BLE001
                not_passed(f"src/estimate.py: {name} raised {type(e).__name__}: {e} (variant {idx})")

            expected = REF_FUNCS[name](variant)
            label = f"{name} (variant {idx})"

            if name == "pod_count":
                if not isinstance(actual, int) and not (isinstance(actual, float) and actual.is_integer()):
                    not_passed(f"{label}: expected an integer pod count, got {actual!r}")
                if int(actual) != expected:
                    not_passed(f"{label}: got {actual!r}, expected {expected!r} (exact integer match)")
            else:
                check_close(actual, expected, rel_tol=1e-6, label=label)

    design_path = TASK_DIR / "DESIGN.md"
    required_sections = [
        "Requirements and SLOs",
        "Architecture",
        "Scheduling and freshness",
        "Data flow",
        "Capacity model",
        "Bottlenecks and failure modes",
        "Evolution at 10x",
        "Hostile review responses",
    ]
    min_chars = {
        "Requirements and SLOs": 400,
        "Architecture": 500,
        "Scheduling and freshness": 400,
        "Data flow": 400,
        "Capacity model": 400,
        "Bottlenecks and failure modes": 500,
        "Evolution at 10x": 350,
        "Hostile review responses": 1800,
        "_default": 300,
    }
    sections = check_sections(design_path, required_sections, min_chars)

    keywords = [
        "scheduler", "queue", "proxy", "retry", "backoff", "jitter",
        "rate limit", "concurrency", "worker pool", "freshness", "TTL",
        "circuit breaker", "dead letter", "stampede", "checkpoint",
        "partition", "sharding", "idempotent", "SLA", "SLO",
        "autoscal", "backpressure", "politeness",
    ]
    full_text = "\n\n".join(sections.values())
    check_keywords(full_text, keywords, min_hits=10, label="DESIGN.md")
    check_quantitative(full_text, min_numbers=20, label="DESIGN.md")

    # min_chars is set well above the longest raw hostile-review question
    # (the longest, Q6, is ~543 chars once restated in the subsection body)
    # specifically so that a subsection consisting of the restated question
    # plus only trivial filler cannot clear the bar on length alone.
    check_answers(
        design_path,
        [f"Q{i}" for i in range(1, 9)],
        min_answered=8,
        min_chars=700,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )

    passed("capacity model verified against 3 workloads; design doc structurally complete")


if __name__ == "__main__":
    main()
