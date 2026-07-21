import copy
import math
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_DIR))

from harness.common import (  # noqa: E402
    check_answers,
    check_estimate_module,
    check_keywords,
    check_quantitative,
    check_sections,
    check_close,
    guarded,
    import_estimate,
    load_workload,
    not_passed,
    passed,
    read_doc,
)

REQUIRED_FUNCS = [
    "total_demand_rps",
    "overcommit_ratio",
    "fair_share_allocation",
    "unsatisfied_tenants",
    "tenant_monthly_cost_usd",
    "tenant_monthly_margin_usd",
    "capacity_rps_for_slo",
    "max_tenants_at_current_capacity",
]

REQUIRED_SECTIONS = [
    "Requirements and tenancy model",
    "Isolation boundaries",
    "Quotas and admission control",
    "Fair-share scheduling",
    "Capacity model",
    "Noisy-neighbour containment",
    "Cost attribution and chargeback",
    "Security and data boundary",
    "Bottlenecks and failure modes",
    "Evolution at 10x",
    "Hostile Review",
]

MIN_CHARS = {
    "Requirements and tenancy model": 350,
    "Isolation boundaries": 400,
    "Quotas and admission control": 350,
    "Fair-share scheduling": 400,
    "Capacity model": 350,
    "Noisy-neighbour containment": 400,
    "Cost attribution and chargeback": 400,
    "Security and data boundary": 400,
    "Bottlenecks and failure modes": 350,
    "Evolution at 10x": 300,
    "Hostile Review": 1600,
}

GROUNDING_KEYWORDS = [
    "tenant", "isolation", "quota", "admission control", "rate limit",
    "token bucket", "fair share", "max-min", "weighted", "noisy neighbour",
    "noisy neighbor", "circuit breaker", "bulkhead", "backpressure",
    "chargeback", "showback", "cost attribution", "row-level security",
    "encryption", "blast radius", "sharding", "horizontal scaling",
    "sla", "proxy pool", "burst", "starvation", "overcommit",
]

QUESTION_IDS = [f"Q{i}" for i in range(1, 9)]


# --------------------------------------------------------------------------
# Independent recomputation of the pinned formulas (see README "Capacity
# model contract"). Deliberately terse -- the spec lives in the README.
# --------------------------------------------------------------------------

def _usable(w):
    return w["platform_capacity_rps"] * w["target_utilization"]


def _total_demand(w):
    return sum(t["demand_rps"] for t in w["tenants"].values())


def _overcommit(w):
    return _total_demand(w) / _usable(w)


def _fair_share(w):
    demand = {tid: t["demand_rps"] for tid, t in w["tenants"].items()}
    weight = {tid: t["weight"] for tid, t in w["tenants"].items()}
    active = set(w["tenants"].keys())
    remaining = _usable(w)
    allocation = {}
    guard = 0
    while active:
        guard += 1
        if guard > 10_000:
            raise RuntimeError("fair-share reference did not converge")
        total_weight = sum(weight[t] for t in active)
        share = {t: remaining * weight[t] / total_weight for t in active}
        satisfied = {t for t in active if share[t] >= demand[t]}
        if not satisfied:
            for t in active:
                allocation[t] = share[t]
            active = set()
        else:
            for t in satisfied:
                allocation[t] = demand[t]
                remaining -= demand[t]
            active -= satisfied
    return allocation


def _unsatisfied(w):
    alloc = _fair_share(w)
    demand = {tid: t["demand_rps"] for tid, t in w["tenants"].items()}
    return sorted(t for t in w["tenants"] if alloc[t] < demand[t])


def _cost(w):
    alloc = _fair_share(w)
    out = {}
    for tid, t in w["tenants"].items():
        monthly_requests = alloc[tid] * w["seconds_per_month"]
        request_cost = (monthly_requests / 1000) * w["cost_per_1k_requests_usd"]
        egress_gb = (monthly_requests * t["avg_response_kb"]) / 1_000_000
        egress_cost = egress_gb * w["cost_per_gb_egress_usd"]
        storage_cost = t["storage_gb"] * w["cost_per_gb_month_storage_usd"]
        out[tid] = request_cost + egress_cost + storage_cost
    return out


def _margin(w):
    cost = _cost(w)
    return {tid: t["plan_price_usd_month"] - cost[tid] for tid, t in w["tenants"].items()}


def _capacity_for_slo(w):
    return _total_demand(w) / w["target_utilization"]


def _max_tenants(w):
    avg_demand = _total_demand(w) / len(w["tenants"])
    headroom = _usable(w) - _total_demand(w)
    if headroom <= 0:
        return 0
    return math.floor(headroom / avg_demand)


def _variants(base):
    variants = [("shipped", base)]

    scaled = copy.deepcopy(base)
    for t in scaled["tenants"].values():
        t["demand_rps"] *= 0.4
    variants.append(("demand_scaled_0.4x", scaled))

    cap_up = copy.deepcopy(base)
    cap_up["platform_capacity_rps"] *= 1.5
    variants.append(("capacity_1.5x", cap_up))

    extra = copy.deepcopy(base)
    extra["tenants"]["falcon_starter"] = {
        "tier": "starter", "weight": 2, "demand_rps": 25.0,
        "avg_response_kb": 20.0, "storage_gb": 60.0,
        "plan_price_usd_month": 1200.0, "burst_allowance_multiplier": 1.4,
    }
    variants.append(("extra_tenant", extra))

    return variants


def _check_dict_result(got, expected, fn_label):
    if not isinstance(got, dict):
        not_passed(f"{fn_label}: expected a dict, got {type(got).__name__}")
    if set(got.keys()) != set(expected.keys()):
        not_passed(
            f"{fn_label}: tenant key set mismatch — got {sorted(got.keys())}, "
            f"expected {sorted(expected.keys())}"
        )
    for tid in expected:
        check_close(got[tid], expected[tid], label=f"{fn_label}[{tid}]")


def _check_capacity_model(task_dir: Path) -> None:
    module = import_estimate(task_dir)
    check_estimate_module(module, REQUIRED_FUNCS)

    base = load_workload(task_dir / "workload.json")
    variants = _variants(base)
    seen_unsatisfied_sets = set()

    for label, w in variants:
        check_close(module.total_demand_rps(w), _total_demand(w), label=f"total_demand_rps[{label}]")
        check_close(module.overcommit_ratio(w), _overcommit(w), label=f"overcommit_ratio[{label}]")

        exp_alloc = _fair_share(w)
        _check_dict_result(module.fair_share_allocation(w), exp_alloc, f"fair_share_allocation[{label}]")

        exp_unsat = _unsatisfied(w)
        got_unsat = module.unsatisfied_tenants(w)
        if not isinstance(got_unsat, list) or list(got_unsat) != exp_unsat:
            not_passed(f"unsatisfied_tenants[{label}]: got {got_unsat!r}, expected {exp_unsat!r}")
        seen_unsatisfied_sets.add(tuple(exp_unsat))

        _check_dict_result(module.tenant_monthly_cost_usd(w), _cost(w), f"tenant_monthly_cost_usd[{label}]")
        _check_dict_result(module.tenant_monthly_margin_usd(w), _margin(w), f"tenant_monthly_margin_usd[{label}]")

        check_close(module.capacity_rps_for_slo(w), _capacity_for_slo(w), label=f"capacity_rps_for_slo[{label}]")

        got_max_t = module.max_tenants_at_current_capacity(w)
        exp_max_t = _max_tenants(w)
        if isinstance(got_max_t, bool) or not isinstance(got_max_t, int) or got_max_t != exp_max_t:
            not_passed(
                f"max_tenants_at_current_capacity[{label}]: got {got_max_t!r}, expected {exp_max_t!r} (int)"
            )

    if len(seen_unsatisfied_sets) < 2:
        not_passed(
            "internal validator error: perturbed workloads did not change the "
            "fair-share unsatisfied set qualitatively"
        )


@guarded
def main() -> None:
    task_dir = Path(__file__).resolve().parents[1]

    _check_capacity_model(task_dir)

    design_path = task_dir / "DESIGN.md"
    check_sections(design_path, REQUIRED_SECTIONS, MIN_CHARS)

    full_text = read_doc(design_path)
    check_keywords(full_text, GROUNDING_KEYWORDS, min_hits=12, label="DESIGN.md")
    check_quantitative(full_text, min_numbers=15, label="DESIGN.md")

    # min_chars is set above the longest restated question in DESIGN.md's
    # own template (~211 chars) so that leaving a question's restatement
    # standing in as its own answer cannot clear the length bar on length
    # alone — common.py's verbatim-copy check only catches a single-line
    # exact duplicate, not a multi-line restatement, so this task pins a
    # stricter min_chars to close that gap for questions long enough to
    # slip past it.
    check_answers(
        design_path,
        QUESTION_IDS,
        min_answered=8,
        min_chars=260,
        questions_path=TASK_DIR / "HOSTILE-REVIEW.md",
    )

    passed()


if __name__ == "__main__":
    main()
