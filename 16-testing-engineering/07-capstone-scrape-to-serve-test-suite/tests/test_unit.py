"""YOUR DELIVERABLE (CP1) -- unit + property tests for the pure parser layer.

Read `src/impl.py` first -- `parse_price` and `normalize_record`'s
docstrings are the contract. Import from `src.sut`, not `src.impl`:

    from src.sut import parse_price, normalize_record, Price

These two functions are pure (no I/O, no fixtures needed) -- this file
does not use anything from `conftest.py` and does not need Docker at all.

Write real `def test_*():` functions below, and consider `hypothesis`
`@given(...)` property tests as well as concrete example-based tests. This
file currently has none, so `python -m pytest` collects 0 tests and
fails -- that is expected until you add some. See `hints/` if you get
stuck, and `../README.md` for the completion criteria.

Areas the CP1 mutant bank specifically probes -- your suite needs at
least one test that would fail if any of these broke:

  - Thousands vs. decimal separator: `parse_price("$1,234.56")` must be
    1234.56, not 1.23456 or 1234.56... confused with the reverse
    convention.
  - Sign handling: a leading `-` must negate the amount, and must not
    silently drop or double-apply the sign.
  - Currency symbol mapping: `$`/`€`/`£` map to USD/EUR/GBP respectively,
    and no symbol means USD.
  - Malformed input must raise `ValueError` -- it must never silently
    return `None` or a zero/garbage `Price`.
  - `normalize_record` must raise `KeyError` for a missing required key
    (`id`, `title`, `price`, `url`), collapse internal whitespace runs in
    `title` to a single space, and pass through `parse_price`'s result
    faithfully into `price_amount`/`currency`.
"""

from __future__ import annotations

from src.sut import Price, normalize_record, parse_price  # noqa: F401

# TODO: write test_* functions here (and/or hypothesis @given properties).
