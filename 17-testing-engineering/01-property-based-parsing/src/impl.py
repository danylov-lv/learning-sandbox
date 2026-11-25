"""Price/currency parser and formatter for scraped product listings.

Real scraped price text is messy: different sites emit different thousands
and decimal separators, put the currency symbol or ISO code on either side
of the number, and sometimes show negative amounts for refunds/credits.
This module turns that mess into a small typed `Price` (a `Decimal` amount
plus a normalized ISO currency code) and back into a canonical string.

This file is GIVEN and CORRECT. Do not edit it -- your job in this task is
to write a Hypothesis-based test suite (`tests/test_parser.py`) against
`src.sut` (a generated shim that re-exports this module, or a mutant of it
during grading) that would catch a regression here if one were introduced.

Design notes worth reading before you write tests:

- Currency is MANDATORY. There is no default currency -- every recognized
  input carries a currency marker (a symbol such as $, EUR-sign, GBP-sign,
  or JPY-sign, or a 3-letter ISO code like "USD"), and `parse_price` raises
  `ParseError` if it can't find one. A test suite that only ever feeds USD
  input would never notice a mutant that silently hardcodes "USD" for
  everything.
- Separator disambiguation: when both "." and "," appear in the numeric
  part, WHICHEVER ONE APPEARS LAST is the decimal separator and the other
  is a thousands separator to strip (`"1,234.56"` -> dot decimal;
  `"1.234,56"` -> comma decimal). When only "," appears, it's read as a
  decimal separator ONLY if there's exactly one of them and exactly two
  digits after it (`"1234,56"` -> decimal; `"1,234"` -> thousands). A bare
  "." is always decimal. Spaces are always a thousands separator, never a
  decimal one.
- `Decimal` is used throughout, never `float` -- price arithmetic must not
  suffer binary floating-point rounding error.
- `format_price` is the canonical inverse of `parse_price`: it always
  emits `"<CODE> <amount>"` with no thousands separators and `.` as the
  decimal point (e.g. `"EUR -1234.56"`). `parse_price(format_price(p))`
  should reconstruct a `Price` equal to `p` for any `Price` built from a
  known currency code and a `Decimal` amount -- that round trip is exactly
  the kind of invariant Hypothesis is good at checking, and it does not
  require you to reason about every messy real-world input format at once.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

KNOWN_CURRENCIES = frozenset(
    {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY", "INR"}
)

_SYMBOL_TO_CODE = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
}

_ISO_CODE_START_RE = re.compile(r"^([A-Za-z]{3})\b\s*(.*)$")
_ISO_CODE_END_RE = re.compile(r"^(.*\S)\s+([A-Za-z]{3})$")
_AMOUNT_CHARS_RE = re.compile(r"[0-9.,\s]+")


class ParseError(ValueError):
    """Raised whenever raw input can't be parsed into a Price/quantity.

    The parser never returns None, a zero-value Price, or any other
    "silent failure" sentinel on malformed input -- callers can rely on
    "either you get back a valid value, or you get a ParseError".
    """


@dataclass(frozen=True)
class Price:
    amount: Decimal
    currency: str


def parse_price(raw: str) -> Price:
    """Parse messy scraped price text into a `Price`.

    Examples: "$1,234.56", "USD 99.99", "EUR 1.234,56" (EU format),
    "EUR 1 234,56" (space thousands, comma decimal), "-$5.00" (refund).
    Raises `ParseError` on anything that isn't a recognizable price:
    empty/whitespace-only input, no recognizable currency marker, no
    digits, multiple decimal points, stray characters, etc.
    """
    if not isinstance(raw, str):
        raise ParseError(f"expected str, got {type(raw).__name__}")

    s = raw.strip()
    if not s:
        raise ParseError("empty input")

    negative = False
    if s.startswith("-"):
        negative = True
        s = s[1:].lstrip()

    currency, s = _extract_currency(s, raw)
    s = s.strip()

    if s.startswith("-"):
        if negative:
            raise ParseError(f"multiple sign markers in {raw!r}")
        negative = True
        s = s[1:].lstrip()

    if not s:
        raise ParseError(f"missing numeric amount in {raw!r}")

    amount = _parse_amount(s, raw)
    if negative:
        amount = -amount

    return Price(amount=amount, currency=currency)


def format_price(p: Price) -> str:
    """Canonical string form of a `Price`: "<CODE> <amount>", no thousands
    separators, "." as the decimal point. `parse_price(format_price(p))`
    reconstructs a Price equal to `p` for any `Price` with a known
    currency and a Decimal amount.
    """
    if not isinstance(p, Price):
        raise ParseError(f"expected Price, got {type(p).__name__}")
    if p.currency not in KNOWN_CURRENCIES:
        raise ParseError(f"unknown currency code {p.currency!r}")
    return f"{p.currency} {format(p.amount, 'f')}"


def normalize_quantity(raw: str) -> int:
    """Extract a non-negative integer quantity from messy text such as
    "Qty: 3", "3x", "  12 units  ". Raises `ParseError` if no integer is
    present or the value is negative.
    """
    if not isinstance(raw, str):
        raise ParseError(f"expected str, got {type(raw).__name__}")
    s = raw.strip()
    if not s:
        raise ParseError("empty input")

    match = re.search(r"-?\d+", s)
    if not match:
        raise ParseError(f"no integer quantity found in {raw!r}")

    value = int(match.group(0))
    if value < 0:
        raise ParseError(f"quantity must be non-negative: {raw!r}")
    return value


def _extract_currency(s: str, raw: str) -> tuple[str, str]:
    for symbol, code in _SYMBOL_TO_CODE.items():
        if s.startswith(symbol):
            return code, s[len(symbol):]
    for symbol, code in _SYMBOL_TO_CODE.items():
        if s.endswith(symbol):
            return code, s[: -len(symbol)]

    match = _ISO_CODE_START_RE.match(s)
    if match and match.group(1).upper() in KNOWN_CURRENCIES:
        return match.group(1).upper(), match.group(2)

    match = _ISO_CODE_END_RE.match(s)
    if match and match.group(2).upper() in KNOWN_CURRENCIES:
        return match.group(2).upper(), match.group(1)

    raise ParseError(f"no recognizable currency in {raw!r}")


def _parse_amount(s: str, raw: str) -> Decimal:
    s = s.strip()
    if not s or not _AMOUNT_CHARS_RE.fullmatch(s):
        raise ParseError(f"invalid characters in amount {s!r} (from {raw!r})")

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_comma > last_dot:
            decimal_sep, thousands_sep = ",", "."
        else:
            decimal_sep, thousands_sep = ".", ","
        normalized = s.replace(thousands_sep, "").replace(" ", "")
        normalized = normalized.replace(decimal_sep, ".")
    elif has_comma:
        digits_after = s.rsplit(",", 1)[1]
        if s.count(",") == 1 and len(digits_after) == 2:
            normalized = s.replace(" ", "").replace(",", ".")
        else:
            normalized = s.replace(" ", "").replace(",", "")
    else:
        # Bare "." (if present) is always the decimal point; spaces are
        # always thousands separators.
        normalized = s.replace(" ", "")

    if not normalized or normalized.count(".") > 1:
        raise ParseError(f"malformed amount {s!r} (from {raw!r})")

    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ParseError(f"cannot parse amount {s!r} (from {raw!r})") from exc
