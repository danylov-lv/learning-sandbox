"""Back-of-the-envelope capacity model for the client-SLA delivery pipeline.

Every function takes the workload dict (loaded from `workload.json`) as its
first argument. See the task README's "Capacity model contract" section for
the exact, pinned definition of every quantity below — units, rounding
rules, and which rate (average vs peak) feeds which formula. Do not guess a
definition from the function name alone; the README is the spec.

No arithmetic is sketched here on purpose — this file is the scaffold, not
the worked solution.
"""

from __future__ import annotations


def records_per_day_total(w: dict) -> float:
    """Total records ingested across all clients and all tiers, per day.

    Units: records/day.
    """
    raise NotImplementedError


def average_delivery_rps(w: dict) -> float:
    """Average delivery rate across a full 24h day, spread evenly.

    Units: records/second. No rounding — return the exact float.
    """
    raise NotImplementedError


def peak_delivery_rps(w: dict) -> float:
    """Delivery rate during the peak hour, given the workload's peak-hour
    concentration factor.

    Units: records/second. No rounding — return the exact float.
    """
    raise NotImplementedError


def error_budget_minutes_per_month(w: dict, tier: str) -> float:
    """Allowed downtime for one tier's monthly availability target, in
    minutes, over a pinned 30-day month.

    Units: minutes/month. No rounding — return the exact float.
    """
    raise NotImplementedError


def deliveries_per_day(w: dict, tier: str) -> float:
    """Number of delivery batches per day for one tier, given its total
    daily record volume and its delivery batch size.

    Units: batches/day. No rounding — return the exact float (a fractional
    batch count is expected and meaningful here, not an error).
    """
    raise NotImplementedError


def backlog_after_outage(w: dict) -> float:
    """Records accumulated during the outage window.

    Units: records (a count, but returned as float per the signature).
    """
    raise NotImplementedError


def drain_seconds_after_outage(w: dict) -> float:
    """Wall-clock time to clear the post-outage backlog while the pipeline
    continues serving live traffic concurrently.

    Units: seconds. No rounding — return the exact float.
    """
    raise NotImplementedError


def freshness_breach_count(w: dict) -> int:
    """Number of tiers (0-3) whose freshness deadline is blown through by
    the time it takes to fully recover from the outage (outage window plus
    drain time).

    Units: count of tiers, an integer.
    """
    raise NotImplementedError


def monthly_penalty_usd(w: dict) -> float:
    """Total monthly contractual penalty owed, from the workload's observed
    per-tier breach counts and per-tier penalty-per-breach.

    Units: USD/month. No rounding — return the exact float.
    """
    raise NotImplementedError
