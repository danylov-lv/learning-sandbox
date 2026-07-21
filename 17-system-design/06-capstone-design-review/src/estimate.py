"""Capacity model for the price intelligence platform capstone.

Every function takes the workload dict (loaded from `workload.json`, or a
perturbed in-memory variant of it) as its first argument and returns a
plain number (or a dict of plain numbers) computed from that dict alone --
no hidden constants, no reading `workload.json` from disk inside these
functions.

The exact formula for each function -- including which fields it reads,
the unit conventions (GB = 1e9 bytes, a month = 30 days, a day = 86400
seconds, a year = 365 days), and the rounding rule -- is pinned in this
task's README.md under "Capacity model contract". Read that section
before implementing anything here; this module intentionally does not
restate the arithmetic.

Do not hardcode any number that happens to match `workload.json` as
shipped -- the validator calls every function against the committed
workload AND against several perturbed variants built in memory, and
compares against its own independent recomputation of the same formula.
A hardcoded return value will pass on the shipped file and fail on the
first perturbation.
"""

from __future__ import annotations


def required_fetch_capacity_per_sec(workload: dict) -> float:
    """Average fetch throughput, in fetches/second, the acquisition fleet
    must sustain to refresh every tracked URL at its tier's cadence,
    including the expected retry overhead from `success_rate_first_attempt`
    and `max_attempts`.

    Units: fetches/second (float). No rounding -- this is a continuous
    rate, not a count of discrete things.
    """
    raise NotImplementedError


def fleet_size(workload: dict) -> int:
    """Number of worker pods needed to sustain `required_fetch_capacity_per_sec`
    at `ops.target_utilization`, given each pod's fetch throughput implied
    by `worker_concurrency_per_pod` and `avg_fetch_latency_ms`.

    Units: whole pods (int). Round UP to the next whole pod -- a fleet
    cannot run a fractional pod.
    """
    raise NotImplementedError


def monthly_egress_gb(workload: dict) -> float:
    """Total network egress in one month, in decimal gigabytes (1 GB =
    1e9 bytes), summing acquisition egress (fetch bytes for every attempt,
    including retries) and delivery egress (normalized records shipped to
    every tenant across every client tier).

    Units: GB/month (float). No rounding.
    """
    raise NotImplementedError


def storage_hot_bytes(workload: dict) -> int:
    """Bytes occupied by the hot storage tier: normalized rows ingested
    over `storage.hot_tier_window_days`, compressed at
    `storage.hot_compression_ratio`. Ingestion volume is the *logical*
    refresh rate (one row per successful tier-cadence refresh) -- retries
    do not produce extra stored rows.

    Units: bytes (int). Round to the nearest whole byte.
    """
    raise NotImplementedError


def storage_cold_bytes(workload: dict) -> int:
    """Bytes occupied by the cold storage tier: normalized rows covering
    the remainder of `storage.retention_years` (365 days/year) after the
    hot window, compressed at `storage.cold_compression_ratio`.

    Units: bytes (int). Round to the nearest whole byte.
    """
    raise NotImplementedError


def monthly_cost_by_component(workload: dict) -> dict:
    """Monthly cost broken out by component, in USD.

    Returns a dict with exactly these keys: `"compute"`, `"proxy"`,
    `"egress"`, `"storage"`. `"proxy"` is the cost of acquisition-side
    fetch bytes at `cost.proxy_usd_per_gb`; `"egress"` is the cost of
    delivery-side bytes to clients at `cost.egress_usd_per_gb`; `"storage"`
    combines the hot and cold tiers at their respective per-GB-month
    rates; `"compute"` is fleet cost at `cost.compute_usd_per_pod_hour`.

    Units: USD/month (float) per key. No rounding.
    """
    raise NotImplementedError


def total_monthly_cost(workload: dict) -> float:
    """Total monthly cost in USD: the sum of every value in
    `monthly_cost_by_component(workload)`.

    Units: USD/month (float). No rounding.
    """
    raise NotImplementedError


def cost_per_delivered_record(workload: dict) -> float:
    """Total monthly cost divided by the total number of records
    delivered to all tenants across all client tiers in one month.

    Units: USD per delivered record (float). No rounding.
    """
    raise NotImplementedError


def peak_delivery_rate(workload: dict) -> float:
    """Delivery throughput, in records/second, the delivery path must
    sustain at peak, i.e. the average delivery rate scaled by
    `ops.peak_hour_factor`.

    Units: records/second (float). No rounding.
    """
    raise NotImplementedError


def utilization_at_peak(workload: dict) -> float:
    """Fraction of the acquisition fleet's raw fetch capacity (fleet size
    times per-pod throughput, NOT scaled by `target_utilization`) consumed
    at peak load (`required_fetch_capacity_per_sec` scaled by
    `ops.peak_hour_factor`).

    Units: dimensionless ratio (float). Values above 1.0 are valid and
    meaningful -- they mean peak demand exceeds raw fleet capacity. No
    rounding, and do not clamp to 1.0.
    """
    raise NotImplementedError


def fleet_size_at_10x(workload: dict) -> int:
    """`fleet_size`, recomputed against a derived workload where
    `acquisition.total_tracked_urls` is multiplied by
    `ops.growth_multiplier_10x`, all other fields unchanged.

    Units: whole pods (int). Round UP to the next whole pod, same rule as
    `fleet_size`.
    """
    raise NotImplementedError


def storage_and_cost_at_10x(workload: dict) -> dict:
    """Storage footprint and monthly cost at 10x growth, recomputed
    against a derived workload where BOTH `acquisition.total_tracked_urls`
    and `clients.tenant_count` are multiplied by
    `ops.growth_multiplier_10x`, all other fields unchanged.

    Returns a dict with exactly these keys:
    - `"storage_bytes"`: hot + cold storage bytes at 10x (int, each tier
      rounded the same way as `storage_hot_bytes` / `storage_cold_bytes`,
      then summed).
    - `"monthly_cost"`: `total_monthly_cost` at 10x (float, no rounding).
    """
    raise NotImplementedError
