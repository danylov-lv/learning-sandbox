"""Validator for 17-system-design task 05 -- outage-postmortem-redesign.

Two independent gates, both must pass:

1. Capacity model (src/estimate.py) -- each of the nine required functions
   is called against the committed workload.json plus two perturbed
   variants built in-process here. Expected values are recomputed
   independently (this file's own arithmetic, never importing
   src/estimate.py's formulas) and compared via harness.common.check_close.
   A hardcoded constant return value agrees with the committed workload by
   construction but disagrees on the perturbed ones.
2. Document gate (DESIGN.md) -- required sections present and long enough,
   grounding keywords present in the Causal chain and Redesign sections
   specifically, quantitative claims present, and all eight hostile-review
   questions genuinely answered.

Run from the module root (17-system-design/):

    uv run python 05-outage-postmortem-redesign/tests/validate.py
"""

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
    passed,
)

WORKLOAD_PATH = TASK_DIR / "workload.json"
DESIGN_PATH = TASK_DIR / "DESIGN.md"

REQUIRED_FUNCTIONS = [
    "retry_amplification_factor",
    "effective_ingest_rps",
    "queue_growth_rps",
    "queue_depth_at_minute",
    "peak_queue_depth",
    "connections_demanded",
    "pool_saturation_ratio",
    "drain_seconds",
    "error_budget_burn_fraction",
]


# --------------------------------------------------------------------------
# Gate 1: independent recomputation of the pinned formulas (see README.md
# "Quantitative model contract" -- this arithmetic must match that prose).
# --------------------------------------------------------------------------

def _amp(w):
    p = w["failure_onset_fraction"]
    return (1 - p) * 1 + p * w["retry_max_attempts"]


def _eff_rps(w):
    return w["steady_state_ingest_rps"] * _amp(w)


def _capacity_rps(w):
    return w["worker_count"] * w["concurrency_per_worker"] / w["avg_attempt_seconds"]


def _growth_rps(w):
    return _eff_rps(w) - _capacity_rps(w)


def _qdepth(w, minute):
    return w["initial_queue_depth"] + _growth_rps(w) * 60 * minute


def _peak_q(w):
    return _qdepth(w, w["onset_to_fix_minutes"])


def _conn_demand(w):
    return (
        w["worker_count"]
        * w["concurrency_per_worker"]
        * (w["db_connection_hold_ms"] / 1000.0)
        / w["avg_attempt_seconds"]
    )


def _pool_ratio(w):
    return _conn_demand(w) / w["db_pool_size"]


def _drain_s(w):
    return _peak_q(w) / (w["drain_capacity_rps"] - w["steady_state_ingest_rps"])


def _burn(w):
    seconds_per_month = w["days_per_month"] * 24 * 3600
    monthly_budget = (
        w["delivery_api_rps"] * seconds_per_month * (1 - w["delivery_api_availability_target"])
    )
    incident_errors = (
        w["delivery_api_rps"]
        * (w["delivery_api_impact_minutes"] * 60)
        * w["delivery_api_error_rate_during_incident"]
    )
    return incident_errors / monthly_budget


def _make_variants(base):
    variant_a = dict(base)
    variant_a.update(
        steady_state_ingest_rps=84.0,
        failure_onset_fraction=0.5,
        retry_max_attempts=4,
        worker_count=30,
        concurrency_per_worker=3,
        avg_attempt_seconds=0.5,
        db_connection_hold_ms=300,
        db_pool_size=40,
        initial_queue_depth=1200,
        onset_to_fix_minutes=90,
        drain_capacity_rps=500,
        delivery_api_rps=120,
        delivery_api_availability_target=0.995,
        delivery_api_error_rate_during_incident=0.4,
        delivery_api_impact_minutes=60,
        days_per_month=31,
    )

    variant_b = dict(base)
    variant_b.update(
        steady_state_ingest_rps=42.0,
        failure_onset_fraction=0.2,
        retry_max_attempts=3,
        worker_count=15,
        concurrency_per_worker=6,
        avg_attempt_seconds=0.8,
        db_connection_hold_ms=150,
        db_pool_size=25,
        initial_queue_depth=300,
        onset_to_fix_minutes=200,
        drain_capacity_rps=250,
        delivery_api_rps=50,
        delivery_api_availability_target=0.9995,
        delivery_api_error_rate_during_incident=0.8,
        delivery_api_impact_minutes=150,
        days_per_month=28,
    )

    return [("shipped", base), ("variant-a", variant_a), ("variant-b", variant_b)]


def check_capacity_model(task_dir):
    module = import_estimate(task_dir)
    check_estimate_module(module, REQUIRED_FUNCTIONS)

    base = load_workload(WORKLOAD_PATH)
    variants = _make_variants(base)

    for label, w in variants:
        check_close(
            module.retry_amplification_factor(w), _amp(w),
            label=f"{label}: retry_amplification_factor",
        )
        check_close(
            module.effective_ingest_rps(w), _eff_rps(w),
            label=f"{label}: effective_ingest_rps",
        )
        check_close(
            module.queue_growth_rps(w), _growth_rps(w),
            label=f"{label}: queue_growth_rps",
        )

        for minute in (0, 17.5, w["onset_to_fix_minutes"]):
            check_close(
                module.queue_depth_at_minute(w, minute), _qdepth(w, minute),
                label=f"{label}: queue_depth_at_minute(minute={minute})",
            )

        check_close(
            module.peak_queue_depth(w), _peak_q(w),
            label=f"{label}: peak_queue_depth",
        )
        check_close(
            module.connections_demanded(w), _conn_demand(w),
            label=f"{label}: connections_demanded",
        )
        check_close(
            module.pool_saturation_ratio(w), _pool_ratio(w),
            label=f"{label}: pool_saturation_ratio",
        )
        check_close(
            module.drain_seconds(w), _drain_s(w),
            label=f"{label}: drain_seconds",
        )
        check_close(
            module.error_budget_burn_fraction(w), _burn(w),
            label=f"{label}: error_budget_burn_fraction",
        )


# --------------------------------------------------------------------------
# Gate 2: DESIGN.md structure
# --------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "Incident summary",
    "Causal chain",
    "Quantified analysis",
    "Contributing factors",
    "Redesign",
    "Blast radius and isolation",
    "Detection and alerting",
    "Verification plan",
    "Hostile Review",
]

MIN_CHARS = {
    "_default": 200,
    "Causal chain": 700,
    "Redesign": 700,
    "Hostile Review": 1700,
}

CAUSAL_CHAIN_KEYWORDS = [
    "retry", "requeue", "backoff", "amplif", "parse", "degraded",
    "connection pool", "pool", "autoscal", "delivery-api", "delivery api",
    "cascad", "bulkhead", "queue depth", "dead letter", "dlq", "saturat",
]
REDESIGN_KEYWORDS = [
    "circuit breaker", "bulkhead", "backoff", "jitter", "dead letter",
    "dlq", "pool", "isolat", "rate limit", "autoscal", "idempot",
    "dedicat",
]

QUESTION_IDS = [f"Q{i}" for i in range(1, 9)]


def check_document(design_path):
    sections = check_sections(design_path, REQUIRED_SECTIONS, MIN_CHARS)

    check_keywords(
        sections["Causal chain"], CAUSAL_CHAIN_KEYWORDS, min_hits=5,
        label="'Causal chain' grounding",
    )
    check_keywords(
        sections["Redesign"], REDESIGN_KEYWORDS, min_hits=4,
        label="'Redesign' grounding",
    )
    check_quantitative(
        sections["Quantified analysis"], min_numbers=6,
        label="'Quantified analysis' quantitative claims",
    )

    check_answers(
        design_path,
        QUESTION_IDS,
        min_answered=8,
        min_chars=200,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )


@guarded
def main():
    check_capacity_model(TASK_DIR)
    check_document(DESIGN_PATH)
    passed("capacity model matches across 3 workloads; DESIGN.md complete")


if __name__ == "__main__":
    main()
