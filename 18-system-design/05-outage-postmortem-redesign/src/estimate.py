"""Capacity model for the outage in ../INCIDENT.md.

Every function takes the workload dict (see ../workload.json) as its first
argument. The exact formula for each function is pinned in ../README.md's
"Quantitative model contract" section -- this module states only the
contract (inputs, units, output units, rounding rule) for each function.
Do not guess the formula from the field names alone; read the README.

No arithmetic is worked out here or in the README's examples. Read the
committed workload.json and INCIDENT.md to understand what each field
means before wiring the formulas together.
"""

from __future__ import annotations


def retry_amplification_factor(w: dict) -> float:
    """Effective attempts delivered per originally-ingested message, given
    the workload's failure onset fraction and retry policy.

    Units: dimensionless (attempts per message), >= 1.0.
    Rounding: none -- return the exact float.
    See README "Quantitative model contract" for the precise definition of
    which messages are assumed to exhaust every retry attempt and which are
    assumed to succeed on the first attempt.
    """
    raise NotImplementedError


def effective_ingest_rps(w: dict) -> float:
    """Offered load on the worker fleet after retry amplification, i.e. the
    rate of delivery attempts (original + retries) workers must process per
    second, given the workload's steady-state ingest rate.

    Units: attempts/second.
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def queue_growth_rps(w: dict) -> float:
    """Net rate at which the queue backlog grows: offered load minus the
    worker fleet's processing capacity, at the workload's given (peak)
    fleet size.

    Units: messages/second. Positive means the backlog is growing;
    negative or zero means the fleet is keeping up.
    Rounding: none -- return the exact float (may be negative).
    """
    raise NotImplementedError


def queue_depth_at_minute(w: dict, minute: float) -> float:
    """Backlog size at a given minute of the incident, under the linear
    single-phase model pinned in the README (constant growth rate from the
    workload's initial queue depth at minute 0).

    Units: messages (as a float; do not round to int).
    `minute` is minutes elapsed since incident onset (minute 0), and may be
    fractional.
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def peak_queue_depth(w: dict) -> float:
    """Backlog size at the moment of manual intervention (the workload's
    onset-to-fix duration), i.e. the highest backlog the linear model
    reaches before the fault is addressed.

    Units: messages (float).
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def connections_demanded(w: dict) -> float:
    """Concurrent DB connections implied by the worker fleet at peak (the
    workload's given peak worker count and per-worker concurrency), given
    how much of each attempt's duration holds a DB connection.

    Units: connections (float, not rounded to int -- this is an expected
    concurrent occupancy, not a headcount).
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def pool_saturation_ratio(w: dict) -> float:
    """Connections demanded (see `connections_demanded`) against the
    workload's configured DB pool size.

    Units: dimensionless ratio. A value > 1.0 means the fleet demands more
    concurrent connections than the pool can hand out.
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def drain_seconds(w: dict) -> float:
    """Time to clear the peak backlog once the fault is fixed, given the
    workload's drain capacity and the fact that live (non-amplified,
    steady-state) traffic keeps arriving throughout the drain.

    Units: seconds.
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError


def error_budget_burn_fraction(w: dict) -> float:
    """Share of the delivery API's monthly error budget consumed by this
    incident, given its request rate, availability target, the error rate
    it actually ran at during the impacted window, and how long that
    window lasted.

    Units: dimensionless fraction of one month's error budget (values > 1.0
    mean the incident alone exceeded the entire monthly budget).
    Rounding: none -- return the exact float.
    """
    raise NotImplementedError
