"""Reference classifier shared by make_drill_day.py and validate.py.

This is test/harness infrastructure, not a DAG solution: it encodes the exact
same business rules stated in README.md (and given as constants in
src/t04_quarantine_and_alerts.py) so that drill-data generation and
validation agree on what "valid", "invalid", and "malformed" mean for a raw
line. It does not touch Postgres, Airflow, or the alert sink.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

ALLOWED_CURRENCIES = {"USD", "EUR", "GBP"}

CATEGORY_PRICE_CEILING = {
    "electronics": 9730,
    "home-goods": 2290,
    "kitchen": 1410,
    "toys": 1000,
    "sporting-goods": 2800,
    "office-supplies": 470,
    "beauty": 630,
    "grocery": 200,
    "pet-supplies": 570,
    "tools": 2030,
    "furniture": 16070,
    "apparel": 1210,
}


def classify_line(raw_line: str, dt: str):
    """Return ("malformed", None), ("invalid", reason, record), or
    ("valid", record) for one raw NDJSON line, applying the rules from
    README.md in the fixed order documented there.
    """
    try:
        record = json.loads(raw_line)
    except json.JSONDecodeError:
        return ("malformed", None)

    if "product_url" not in record or record.get("product_url") is None:
        return ("invalid", "missing_product_url", record)

    price = record.get("price")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        category = record.get("category")
        ceiling = CATEGORY_PRICE_CEILING.get(category)
        if price <= 0 or (ceiling is not None and price > ceiling):
            return ("invalid", "invalid_price", record)

    if record.get("currency") not in ALLOWED_CURRENCIES:
        return ("invalid", "unknown_currency", record)

    scraped_at = record.get("scraped_at")
    try:
        scraped_dt = datetime.fromisoformat(scraped_at.replace("Z", "+00:00"))
        scraped_date = scraped_dt.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, AttributeError):
        return ("invalid", "invalid_scraped_at", record)

    if scraped_date != dt:
        return ("invalid", "invalid_scraped_at", record)

    return ("valid", record)


def classify_file(path, dt: str):
    """Classify every line of an NDJSON file. Returns a dict with counts and
    the list of 0-based line indices that classified as "valid" (useful for
    drill-data corruption, which must never touch malformed or invalid
    lines).
    """
    malformed = 0
    invalid_by_reason = {
        "missing_product_url": 0,
        "invalid_price": 0,
        "unknown_currency": 0,
        "invalid_scraped_at": 0,
    }
    valid = 0
    valid_line_indices = []

    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            outcome = classify_line(line, dt)
            if outcome[0] == "malformed":
                malformed += 1
            elif outcome[0] == "invalid":
                invalid_by_reason[outcome[1]] += 1
                valid += 0
            else:
                valid += 1
                valid_line_indices.append(i)

    invalid_total = sum(invalid_by_reason.values())
    return {
        "total_lines": malformed + invalid_total + valid,
        "malformed": malformed,
        "invalid_total": invalid_total,
        "invalid_by_reason": invalid_by_reason,
        "valid": valid,
        "valid_line_indices": valid_line_indices,
    }
