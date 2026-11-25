"""Starting test suite for `target.py` — green, but weak.

This suite passes against the correct implementation, but it only exercises
one happy path per function: no boundaries, no error paths, no false
branches. Running `cosmic-ray` against it (see the README) leaves several
mutants alive. Your job is to EDIT this file, adding tests until zero
mutants survive.
"""

from target import apply_discount, classify_price_tier, is_valid_sku, shipping_cost


def test_apply_discount_happy_path():
    assert apply_discount(300.0, 10.0, min_price=50.0) == 270.0


def test_classify_price_tier_happy_path():
    assert classify_price_tier(50.0) == "standard"


def test_is_valid_sku_happy_path():
    assert is_valid_sku("ABC-1234") is True


def test_shipping_cost_happy_path():
    assert shipping_cost(10.0, distance_km=20.0) == 27.0
