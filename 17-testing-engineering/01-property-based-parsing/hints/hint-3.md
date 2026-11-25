No ready-made test code here -- just the concrete pieces to assemble
yourself.

**The `Price` strategy.** `st.decimals(min_value=..., max_value=...,
places=2, allow_nan=False, allow_infinity=False)` gives you Decimals with
exactly two decimal places, which keeps things simple and matches how
real prices look. Pick a `min_value`/`max_value` range wide enough to
include negative amounts (refunds) -- something like `-999999.99` to
`999999.99`. Pair that with `st.sampled_from(sorted(KNOWN_CURRENCIES))`
for currency, and combine both with `st.builds(Price, amount=...,
currency=...)`.

**Formatting a Decimal for the EU-style metamorphic test.** You need the
same numeric value spelled two ways. Format the Decimal with `format(x,
'f')` (not `str(x)` -- `str` can fall back to scientific notation for some
Decimals, which isn't a real-world price format and isn't worth chasing).
That gives you a plain `"1234.56"`-style string with `.` as the decimal
point and no thousands separators; to make an EU-style string out of it,
just swap that single `.` for a `,` (there won't be any thousands
separators to worry about if you built the Decimal directly rather than
parsing it from messy text).

**The "garbage always raises `ParseError`" property.** The risk with
`st.text()` is that Hypothesis might occasionally produce something that
coincidentally parses as a real price (e.g. it generates the literal
string `"USD 5"`), which would make your "this must raise" assumption
wrong through no fault of the parser. Handle that by catching whatever
`parse_price` actually does inside the test body instead of asserting
before calling it: if it raises `ParseError`, that's fine, test passes; if
it raises anything else, that's a failure (wrong exception type); if it
returns without raising, that's only a failure if you can also see the
input wasn't in fact a parseable price -- easiest way to sidestep this
entirely is `assume()`-ing away inputs that contain a currency symbol or
any 3-letter substring matching a known code, before the input reaches
`parse_price` at all.

**Concrete pins.** Look at the exact example strings quoted in
`src/impl.py`'s docstring -- `"$1,234.56"`, `"EUR 1.234,56"`, `"-$5.00"`
-- and write one plain `assert parse_price(...) == Price(Decimal("..."),
"...")` per format family you care about pinning down, plus one for a
lowercase currency code (`"usd 99.99"`) and one for an amount with
multiple decimal points that must raise (`"$12.34.56"`).
