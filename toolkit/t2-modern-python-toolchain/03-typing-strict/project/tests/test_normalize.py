"""Given, not edited. Pins the behavior that must survive your typing fixes."""

import pytest

from normkit.normalize import (
    batch_normalize,
    clean_price,
    parse_optional_tag,
    to_currency_code,
)


def test_clean_price_strips_currency_and_commas() -> None:
    assert clean_price("$1,234.56") == 1234.56
    assert clean_price(" 9.99 ") == 9.99


def test_parse_optional_tag_with_value() -> None:
    assert parse_optional_tag(" Clearance ") == "clearance"


def test_parse_optional_tag_with_none() -> None:
    assert parse_optional_tag(None) == ""


def test_to_currency_code_valid() -> None:
    assert to_currency_code("usd") == "USD"


def test_to_currency_code_invalid_raises() -> None:
    with pytest.raises(ValueError):
        to_currency_code("dollars")


def test_batch_normalize() -> None:
    assert batch_normalize(["$1.00", "$2.50"]) == [1.0, 2.5]
