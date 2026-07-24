# priceparser

A tiny library that parses human-typed price strings (`"$1,234.56"`,
`"EUR 1.234,56"`, `"-$5.00"`) into `(amount_cents, currency_code)` tuples,
and formats them back.

## Run the tests

From this directory (`sample-project/`):

```bash
uv run pytest tests -q
```

## Layout

- `src/priceparser/__init__.py` — `parse_price` and `format_price`.
- `tests/test_priceparser.py` — the test suite.

## Conventions used in this code (for reference — do not edit this project)

- Money is always represented as **integer cents**, never `float`. Floats
  lose cents to binary rounding; integers don't.
- `parse_price` never raises. Malformed input returns `None`. Callers
  check for `None`, they don't wrap calls in `try/except`.
- Currency codes are always normalized to uppercase 3-letter ISO codes
  from `KNOWN_CURRENCIES` (`USD`, `EUR`, `GBP`). Unknown codes parse to
  `None`, not a passthrough.
