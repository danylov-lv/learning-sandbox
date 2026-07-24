import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from priceparser import format_price, parse_price  # noqa: E402


def test_parses_us_style_dollar():
    assert parse_price("$1,234.56") == (123456, "USD")


def test_parses_eu_style_euro_code():
    assert parse_price("EUR 1.234,56") == (123456, "EUR")


def test_parses_refund_as_negative():
    assert parse_price("-$5.00") == (-500, "USD")


def test_lowercase_currency_code():
    assert parse_price("usd 99.99") == (9999, "USD")


def test_unknown_currency_code_returns_none():
    assert parse_price("XYZ 5.00") is None


def test_garbage_returns_none_not_exception():
    assert parse_price("not a price") is None
    assert parse_price("") is None
    assert parse_price(None) is None  # type: ignore[arg-type]


def test_format_round_trip():
    assert format_price(*parse_price("$1,234.56")) == "$1234.56"


def test_format_negative():
    assert format_price(-500, "USD") == "-$5.00"
