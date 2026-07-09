"""Shared constants for the PriceWatch event harness.

Used by events.py (generation), ground_truth.py (reference answers), and
validate.py (structural checks). Keeping these in one place means the
generator and the ground-truth computation can never silently drift apart.
"""

from datetime import datetime, timezone

START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2026, 1, 1, tzinfo=timezone.utc)
SPAN_DAYS = (END_DATE - START_DATE).days

CATEGORIES = [
    "electronics",
    "home-appliances",
    "kitchen",
    "toys",
    "sporting-goods",
    "office-supplies",
    "beauty",
    "grocery",
    "pet-supplies",
    "tools",
    "furniture",
    "footwear",
    "apparel",
    "books",
    "garden",
]

BRANDS = [
    "Northwind",
    "Vertex",
    "Solace",
    "Marlowe",
    "Iron Fox",
    "Blue Harbor",
    "Cedarline",
    "Quartz",
    "Redshift",
    "Amberly",
    "Foxglove",
    "Greystone",
    "Halcyon",
    "Ivory Road",
    "Junction",
    "Kestrel",
    "Lumen",
    "Meridian",
    "Novus",
    "Outland",
]

COUNTRIES = ["US", "DE", "GB", "FR", "NL", "PL", "ES", "IT"]

TIERS = ["bronze", "silver", "gold"]
TIER_WEIGHTS = [0.5, 0.35, 0.15]

CURRENCIES = ["USD", "EUR", "GBP"]
CURRENCY_WEIGHTS = [0.7, 0.2, 0.1]

# Fixed FX table, USD base. Deliberately static (no historical FX drift) --
# the point of the module is schema design, not currency-conversion accuracy.
FX_TO_USD = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
}


def to_usd(amount: float, currency: str) -> float:
    return round(amount * FX_TO_USD[currency], 4)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
