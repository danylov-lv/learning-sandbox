# Your test suite goes here.
#
# Import the system under test from `src.sut`, never from `src.impl`
# directly -- see src/sut.py and the module design notes if you're curious
# why, but the short version is: `src.sut` is how the grader swaps in a
# mutant implementation without your test file needing to know about it.
#
#   from src.sut import KNOWN_CURRENCIES, ParseError, Price, format_price, parse_price
#
# What to write: property-based tests using Hypothesis (`from hypothesis
# import given, assume, strategies as st`), plus a handful of concrete
# example tests for cases worth pinning down explicitly. Read
# 01-property-based-parsing/README.md for the full brief and
# hints/hint-1.md through hint-3.md if you get stuck -- do not open
# .authoring/ before you're done, it contains the answer key.
#
# Rough shape to aim for (delete this comment block once you have real
# tests):
#
#   - A strategy that builds arbitrary `Price` values (currency drawn from
#     KNOWN_CURRENCIES, amount drawn from st.decimals with a fixed number
#     of places) and a `@given` test asserting the round trip:
#     parse_price(format_price(p)) == p
#   - A property asserting every malformed input raises ParseError -- never
#     None, never a wrong type, never a silently-zero Price.
#   - At least one concrete example test per messy real-world format you
#     read about in src/impl.py's module docstring (US thousands/decimal,
#     EU thousands/decimal, a negative/refund price, a lowercase currency
#     code) -- Hypothesis's random search is not guaranteed to happen to
#     generate the exact edge case you care about, so pin the ones that
#     matter with a plain example.
#
# This file currently collects zero tests on purpose -- `uv run python
# 01-property-based-parsing/tests/validate.py` is expected to fail cleanly
# against this stub. That is the starting state, not a bug.
