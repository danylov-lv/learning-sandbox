"""Capacity/allocation model for the multi-tenant scraping platform.

Every function takes the loaded `workload.json` dict as its single
argument. The exact formula for each function is pinned in the task
README (section "Capacity model contract") -- it is not repeated here.
No arithmetic is hinted at in this file; only contracts (inputs, units,
output shape, rounding).
"""

from __future__ import annotations


def total_demand_rps(w: dict) -> float:
    """Sum of demanded request rate across all tenants.

    Units: requests/second. Returns a plain float, unrounded.
    """
    raise NotImplementedError


def overcommit_ratio(w: dict) -> float:
    """Total demand against usable capacity (capacity after headroom).

    Units: dimensionless ratio. >1.0 means demand exceeds usable capacity.
    Returns a plain float, unrounded.
    """
    raise NotImplementedError


def fair_share_allocation(w: dict) -> dict[str, float]:
    """Weighted max-min fair share of usable capacity across tenants.

    See README "Capacity model contract" for the exact progressive-filling
    algorithm, including the satisfied/unsatisfied tie rule.

    Units: requests/second per tenant. Returns {tenant_id: allocated_rps},
    one entry per tenant id in w["tenants"], unrounded floats.
    """
    raise NotImplementedError


def unsatisfied_tenants(w: dict) -> list[str]:
    """Tenant ids allocated strictly less than they demanded.

    Returns a list of tenant ids sorted ascending (lexicographic).
    """
    raise NotImplementedError


def tenant_monthly_cost_usd(w: dict) -> dict[str, float]:
    """Attributed infrastructure cost per tenant at its allocated rate.

    Combines request cost, egress cost, and storage cost per the README's
    per-unit cost formulas. Units: USD/month. Returns
    {tenant_id: total_cost_usd}, unrounded floats.
    """
    raise NotImplementedError


def tenant_monthly_margin_usd(w: dict) -> dict[str, float]:
    """Plan price minus attributed cost, per tenant.

    Units: USD/month. Can be negative. Returns {tenant_id: margin_usd},
    unrounded floats.
    """
    raise NotImplementedError


def capacity_rps_for_slo(w: dict) -> float:
    """The platform capacity that would satisfy all demand at the target
    headroom (i.e. the capacity at which overcommit_ratio would be 1.0).

    Units: requests/second. Returns a plain float, unrounded.
    """
    raise NotImplementedError


def max_tenants_at_current_capacity(w: dict) -> int:
    """How many additional average-sized tenants fit before the SLO
    headroom is exceeded.

    "Average-sized" means demand shaped like today's mean tenant demand.
    Units: count of tenants. Returns a plain int (0 if already at or past
    the headroom limit).
    """
    raise NotImplementedError
