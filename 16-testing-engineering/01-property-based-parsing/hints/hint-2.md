The three kinds of promise from hint 1, made concrete:

1. **Round trip.** `format_price` is described as the canonical inverse of
   `parse_price`. Build a Hypothesis strategy that constructs arbitrary
   `Price` objects directly (`st.builds(Price, amount=..., currency=...)`
   -- draw `currency` from `KNOWN_CURRENCIES` via `st.sampled_from`, draw
   `amount` from `st.decimals(...)` with `places=` fixed to a small number
   so you get clean two-decimal-style values), then assert
   `parse_price(format_price(p)) == p`. This one test alone is a strong
   check on a lot of surface area -- it fails if currency gets dropped or
   swapped, if the sign gets lost, if the amount gets rounded or
   truncated.

2. **Error typing on bad input.** Generate arbitrary junk text (plain
   `st.text()`) and assert that `parse_price` either returns a valid
   `Price` or raises `ParseError` -- never anything else (no `None`, no
   other exception type, no silently-wrong value that happens not to
   crash). You'll need `assume()` to rule out junk that might accidentally
   look like a valid price by chance, or just wrap the assertion in a
   try/except that only tolerates `ParseError` and fails loudly on
   anything else, including "no exception at all but the wrong shape of
   result."

3. **Metamorphic: two representations, same value.** Take one Hypothesis-
   generated numeric value and render it TWO different ways yourself
   inside the test -- once in US style (comma thousands, dot decimal),
   once in EU style (dot thousands, comma decimal) -- prefixed with a
   currency code either way. Assert `parse_price` gives the same `amount`
   for both. This is the test that would catch a US-only assumption baked
   into the separator logic; a round-trip test alone might not catch it,
   because round-tripping through `format_price` never produces EU-style
   output to parse back in the first place.

Then add plain example tests for: a European-formatted string, a negative
("refund") price, and a currency code given in lowercase -- pin each down
explicitly with a concrete `assert`.
