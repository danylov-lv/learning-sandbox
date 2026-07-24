"""A tiny price-parsing library. Complete and correct — this is the GIVEN
toy project for the project-memory task; you do not edit this code.

All prices are represented internally as integer cents (never float), to
avoid binary floating-point rounding on money. `parse_price` never raises
on malformed input — it returns None instead, so callers always get a
value they can check rather than having to wrap every call in try/except.
"""

from __future__ import annotations

import re

KNOWN_CURRENCIES = {"USD", "EUR", "GBP"}

_SYMBOL_TO_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP"}

_PRICE_RE = re.compile(
    r"^\s*(?P<sign>-)?\s*(?:(?P<symbol>[$€£])|(?P<code>[A-Za-z]{3})\s+)?"
    r"(?P<amount>\d[\d.,]*\d|\d)\s*$"
)


def parse_price(text: str) -> tuple[int, str] | None:
    """Parse a price string into (amount_cents, currency_code).

    Accepts a leading currency symbol ($, EUR, GBP) or a 3-letter ISO
    code, an optional leading '-' for refunds, and either
    US-style (1,234.56) or EU-style (1.234,56) grouping. Returns None on
    anything it cannot confidently parse — it never raises.
    """
    if not isinstance(text, str):
        return None
    m = _PRICE_RE.match(text)
    if not m:
        return None

    currency = None
    if m.group("symbol"):
        currency = _SYMBOL_TO_CURRENCY[m.group("symbol")]
    elif m.group("code"):
        code = m.group("code").upper()
        if code not in KNOWN_CURRENCIES:
            return None
        currency = code
    else:
        return None

    raw = m.group("amount")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        # A single comma group of exactly 2 digits is EU-style decimals;
        # anything else is a US-style thousands separator.
        head, _, tail = raw.rpartition(",")
        raw = head.replace(",", "") + "." + tail if len(tail) == 2 else raw.replace(",", "")

    try:
        whole, _, frac = raw.partition(".")
        frac = (frac + "00")[:2]
        cents = int(whole) * 100 + int(frac)
    except ValueError:
        return None

    if m.group("sign"):
        cents = -cents
    return cents, currency


def format_price(amount_cents: int, currency: str) -> str:
    """Render (amount_cents, currency) back to a canonical string, e.g.
    format_price(123456, "USD") -> "$1234.56"."""
    sign = "-" if amount_cents < 0 else ""
    whole, frac = divmod(abs(amount_cents), 100)
    symbol = {v: k for k, v in _SYMBOL_TO_CURRENCY.items()}.get(currency, currency + " ")
    return f"{sign}{symbol}{whole}.{frac:02d}"
