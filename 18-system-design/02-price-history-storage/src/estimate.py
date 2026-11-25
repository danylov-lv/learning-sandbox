"""Back-of-the-envelope capacity model for the price-history storage design.

Every function takes the workload dict (loaded from ``workload.json`` at the
task root, or a perturbed variant of it) as its single argument and returns
a plain float. The exact formula for each function is pinned in the task
README's "Capacity model contract" section — units, rounding rule (there is
none: return the raw float, do not round/floor/ceil/truncate anywhere), and
which fields feed which function. Implement the formulas from that section;
do not guess at a different convention.
"""

from __future__ import annotations


def rows_per_day(w: dict) -> float:
    """Total price-observation rows written per day, across all tracked
    products.

    Units: rows/day. See README for the exact formula and which
    `workload.json` fields it consumes.
    """
    raise NotImplementedError


def rows_retained(w: dict) -> float:
    """Total row count held across the full retention window (hot + cold
    tiers combined), at full (non-change-only) observation granularity.

    Units: rows.
    """
    raise NotImplementedError


def raw_bytes_retained(w: dict) -> float:
    """Uncompressed byte footprint of `rows_retained`.

    Units: bytes.
    """
    raise NotImplementedError


def compressed_bytes_retained(w: dict) -> float:
    """Compressed byte footprint of `raw_bytes_retained`.

    Units: bytes.
    """
    raise NotImplementedError


def change_only_rows_per_day(w: dict) -> float:
    """Rows/day if only observations where the price actually changed are
    persisted (the delta/change-only storage variant), instead of every
    observation.

    Units: rows/day.
    """
    raise NotImplementedError


def change_only_compressed_bytes_retained(w: dict) -> float:
    """Compressed byte footprint across the full retention window under the
    change-only storage variant.

    Units: bytes.
    """
    raise NotImplementedError


def hot_tier_bytes(w: dict) -> float:
    """Compressed byte footprint of just the hot-tier window, at full
    (non-change-only) observation granularity.

    Units: bytes.
    """
    raise NotImplementedError


def monthly_storage_cost_usd(w: dict) -> float:
    """Blended monthly storage cost: the hot tier priced at its per-GB rate,
    the remainder of the retention window (cold tier) priced at its own,
    lower, per-GB rate. 1 GB = 1,000,000,000 bytes (decimal), not GiB.

    Units: USD/month.
    """
    raise NotImplementedError


def range_query_bytes_scanned(w: dict) -> float:
    """Bytes scanned to answer the charting read -- one product's full
    price series over a one-year range -- under the designed (good)
    ordering/clustering key.

    Units: bytes.
    """
    raise NotImplementedError
