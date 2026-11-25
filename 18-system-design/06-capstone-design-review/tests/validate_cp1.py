"""CP1 -- requirements/capacity design-doc sections, plus the numeric gate
on `src/estimate.py`.

Two checks, in order:

1. `DESIGN.md` has the five CP1 sections, each long enough, each
   mentioning grounding keywords, each making quantitative claims, none
   still containing a placeholder marker.
2. Every function in `src/estimate.py` is called against the committed
   `workload.json` plus two perturbed variants built in memory here, and
   each result is compared against this validator's own, independently
   written recomputation of the same formula (never importing the
   learner's arithmetic). A hardcoded constant return value will agree
   with this file's recomputation on the shipped workload by
   construction, but diverge on a perturbed one.

Any failure is `NOT PASSED`, naming which check failed.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
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

DESIGN_PATH = TASK_ROOT / "DESIGN.md"
WORKLOAD_PATH = TASK_ROOT / "workload.json"

REQUIRED_SECTIONS = [
    "Problem statement and scope",
    "Requirements, SLIs and SLOs",
    "Workload characterization",
    "Capacity model",
    "Cost model",
]

_MIN_CHARS = 250

_GROUNDING_KEYWORDS = [
    "SLO", "SLI", "freshness", "p95", "p99", "latency", "throughput",
    "retention", "utilization", "peak", "cost per", "hot tier", "cold tier",
    "tenant", "egress", "availability", "backlog", "quota",
]
_MIN_KEYWORD_HITS = 6
_MIN_NUMERIC_TOKENS = 8

REQUIRED_FUNCTIONS = [
    "required_fetch_capacity_per_sec",
    "fleet_size",
    "monthly_egress_gb",
    "storage_hot_bytes",
    "storage_cold_bytes",
    "monthly_cost_by_component",
    "total_monthly_cost",
    "cost_per_delivered_record",
    "peak_delivery_rate",
    "utilization_at_peak",
    "fleet_size_at_10x",
    "storage_and_cost_at_10x",
]


# --------------------------------------------------------------------------
# Independent recomputation of the README's pinned formulas.
# --------------------------------------------------------------------------

def _daily_new_rows(w: dict) -> float:
    acq = w["acquisition"]
    total = acq["total_tracked_urls"]
    return sum(
        total * t["fraction"] * (1440.0 / t["refresh_interval_minutes"])
        for t in acq["tiers"].values()
    )


def _expected_attempts(w: dict) -> float:
    acq = w["acquisition"]
    return 1.0 + (1.0 - acq["success_rate_first_attempt"]) * (acq["max_attempts"] - 1)


def _per_pod_capacity(w: dict) -> float:
    acq = w["acquisition"]
    return acq["worker_concurrency_per_pod"] * 1000.0 / acq["avg_fetch_latency_ms"]


def _required_fetch_capacity_per_sec(w: dict) -> float:
    return _daily_new_rows(w) * _expected_attempts(w) / 86400.0


def _fleet_size(w: dict) -> int:
    cap = _per_pod_capacity(w) * w["ops"]["target_utilization"]
    return math.ceil(_required_fetch_capacity_per_sec(w) / cap)


def _fetch_egress_bytes_per_month(w: dict) -> float:
    acq = w["acquisition"]
    return _daily_new_rows(w) * _expected_attempts(w) * 30.0 * acq["avg_fetch_bytes"]


def _delivery_records_per_month(w: dict) -> float:
    cl = w["clients"]
    per_day = sum(
        cl["tenant_count"] * t["weight"] * t["records_per_delivery"] * t["deliveries_per_day"]
        for t in cl["tiers"]
    )
    return per_day * 30.0


def _delivery_egress_bytes_per_month(w: dict) -> float:
    return _delivery_records_per_month(w) * w["storage"]["avg_row_bytes_normalized"]


def _monthly_egress_gb(w: dict) -> float:
    return (_fetch_egress_bytes_per_month(w) + _delivery_egress_bytes_per_month(w)) / 1e9


def _storage_hot_bytes(w: dict) -> int:
    st = w["storage"]
    raw = _daily_new_rows(w) * st["hot_tier_window_days"] * st["avg_row_bytes_normalized"]
    return round(raw / st["hot_compression_ratio"])


def _storage_cold_bytes(w: dict) -> int:
    st = w["storage"]
    cold_days = st["retention_years"] * 365 - st["hot_tier_window_days"]
    raw = _daily_new_rows(w) * cold_days * st["avg_row_bytes_normalized"]
    return round(raw / st["cold_compression_ratio"])


def _cost_components(w: dict) -> dict:
    cost = w["cost"]
    compute = _fleet_size(w) * 24 * 30 * cost["compute_usd_per_pod_hour"]
    proxy = (_fetch_egress_bytes_per_month(w) / 1e9) * cost["proxy_usd_per_gb"]
    egress = (_delivery_egress_bytes_per_month(w) / 1e9) * cost["egress_usd_per_gb"]
    storage = (
        (_storage_hot_bytes(w) / 1e9) * cost["storage_hot_usd_per_gb_month"]
        + (_storage_cold_bytes(w) / 1e9) * cost["storage_cold_usd_per_gb_month"]
    )
    return {"compute": compute, "proxy": proxy, "egress": egress, "storage": storage}


def _total_monthly_cost(w: dict) -> float:
    return sum(_cost_components(w).values())


def _cost_per_delivered_record(w: dict) -> float:
    return _total_monthly_cost(w) / _delivery_records_per_month(w)


def _peak_delivery_rate(w: dict) -> float:
    return (_delivery_records_per_month(w) / (30.0 * 86400.0)) * w["ops"]["peak_hour_factor"]


def _utilization_at_peak(w: dict) -> float:
    peak = _required_fetch_capacity_per_sec(w) * w["ops"]["peak_hour_factor"]
    raw_capacity = _fleet_size(w) * _per_pod_capacity(w)
    return peak / raw_capacity


def _grown(w: dict) -> dict:
    g = copy.deepcopy(w)
    mult = w["ops"]["growth_multiplier_10x"]
    g["acquisition"]["total_tracked_urls"] = w["acquisition"]["total_tracked_urls"] * mult
    g["clients"]["tenant_count"] = w["clients"]["tenant_count"] * mult
    return g


def _fleet_size_at_10x(w: dict) -> int:
    return _fleet_size(_grown(w))


def _storage_and_cost_at_10x(w: dict) -> dict:
    grown = _grown(w)
    storage_bytes = _storage_hot_bytes(grown) + _storage_cold_bytes(grown)
    return {"storage_bytes": storage_bytes, "monthly_cost": _total_monthly_cost(grown)}


# --------------------------------------------------------------------------
# Perturbed workload variants (anti-hardcode gate).
# --------------------------------------------------------------------------

def _variants(base: dict) -> list:
    variants = [("shipped", base)]

    v1 = copy.deepcopy(base)
    v1["acquisition"]["total_tracked_urls"] = int(base["acquisition"]["total_tracked_urls"] * 2.4)
    v1["storage"]["retention_years"] = base["storage"]["retention_years"] + 2
    v1["clients"]["tenant_count"] = int(base["clients"]["tenant_count"] * 1.6)
    v1["ops"]["peak_hour_factor"] = round(base["ops"]["peak_hour_factor"] * 1.15, 3)
    variants.append(("perturbed-scale-up", v1))

    v2 = copy.deepcopy(base)
    v2["acquisition"]["total_tracked_urls"] = int(base["acquisition"]["total_tracked_urls"] * 0.35)
    v2["acquisition"]["success_rate_first_attempt"] = 0.965
    v2["storage"]["hot_tier_window_days"] = 30
    v2["ops"]["target_utilization"] = 0.55
    v2["ops"]["growth_multiplier_10x"] = 6
    v2["cost"]["proxy_usd_per_gb"] = base["cost"]["proxy_usd_per_gb"] * 0.4
    variants.append(("perturbed-scale-down", v2))

    return variants


def _check_capacity_model() -> None:
    module = import_estimate(TASK_ROOT)
    check_estimate_module(module, REQUIRED_FUNCTIONS)

    base = load_workload(WORKLOAD_PATH)
    variants = _variants(base)
    if len(variants) < 3:
        not_passed("internal error: fewer than 3 workload variants configured")

    scalar_checks = [
        ("required_fetch_capacity_per_sec", _required_fetch_capacity_per_sec, 1e-6),
        ("fleet_size", _fleet_size, 1e-9),
        ("monthly_egress_gb", _monthly_egress_gb, 1e-6),
        ("storage_hot_bytes", _storage_hot_bytes, 1e-6),
        ("storage_cold_bytes", _storage_cold_bytes, 1e-6),
        ("total_monthly_cost", _total_monthly_cost, 1e-6),
        ("cost_per_delivered_record", _cost_per_delivered_record, 1e-6),
        ("peak_delivery_rate", _peak_delivery_rate, 1e-6),
        ("utilization_at_peak", _utilization_at_peak, 1e-6),
        ("fleet_size_at_10x", _fleet_size_at_10x, 1e-9),
    ]

    for label, wl in variants:
        for fn_name, expected_fn, rel_tol in scalar_checks:
            fn = getattr(module, fn_name)
            try:
                actual = fn(copy.deepcopy(wl))
            except NotImplementedError:
                not_passed(f"src/estimate.py: {fn_name} is not implemented")
            except Exception as e:  # noqa: BLE001
                not_passed(f"src/estimate.py: {fn_name}({label}) raised {type(e).__name__}: {e}")
            expected = expected_fn(wl)
            check_close(actual, expected, rel_tol=rel_tol, label=f"{fn_name}({label})")

        try:
            actual_costs = module.monthly_cost_by_component(copy.deepcopy(wl))
        except NotImplementedError:
            not_passed("src/estimate.py: monthly_cost_by_component is not implemented")
        except Exception as e:  # noqa: BLE001
            not_passed(f"src/estimate.py: monthly_cost_by_component({label}) raised {type(e).__name__}: {e}")
        if not isinstance(actual_costs, dict):
            not_passed(f"monthly_cost_by_component({label}): expected a dict, got {type(actual_costs).__name__}")
        expected_costs = _cost_components(wl)
        for key, expected_val in expected_costs.items():
            if key not in actual_costs:
                not_passed(f"monthly_cost_by_component({label}): missing key {key!r}")
            check_close(actual_costs[key], expected_val, rel_tol=1e-6, label=f"monthly_cost_by_component({label})[{key}]")

        try:
            actual_growth = module.storage_and_cost_at_10x(copy.deepcopy(wl))
        except NotImplementedError:
            not_passed("src/estimate.py: storage_and_cost_at_10x is not implemented")
        except Exception as e:  # noqa: BLE001
            not_passed(f"src/estimate.py: storage_and_cost_at_10x({label}) raised {type(e).__name__}: {e}")
        if not isinstance(actual_growth, dict):
            not_passed(f"storage_and_cost_at_10x({label}): expected a dict, got {type(actual_growth).__name__}")
        expected_growth = _storage_and_cost_at_10x(wl)
        for key, expected_val in expected_growth.items():
            if key not in actual_growth:
                not_passed(f"storage_and_cost_at_10x({label}): missing key {key!r}")
            check_close(actual_growth[key], expected_val, rel_tol=1e-6, label=f"storage_and_cost_at_10x({label})[{key}]")


def _check_design_doc() -> None:
    sections = check_sections(DESIGN_PATH, REQUIRED_SECTIONS, _MIN_CHARS)
    text = read_doc(DESIGN_PATH)

    check_keywords(text, _GROUNDING_KEYWORDS, _MIN_KEYWORD_HITS, "DESIGN.md (CP1 sections)")

    quant_body = "\n".join(
        sections[h] for h in ("Capacity model", "Cost model", "Workload characterization")
    )
    check_quantitative(quant_body, _MIN_NUMERIC_TOKENS, "DESIGN.md (Capacity model / Cost model / Workload characterization)")


@guarded
def main() -> None:
    _check_design_doc()
    _check_capacity_model()
    passed("CP1: DESIGN.md requirements/capacity sections filled in, and src/estimate.py matches the pinned formulas across 3 workload variants")


if __name__ == "__main__":
    main()
