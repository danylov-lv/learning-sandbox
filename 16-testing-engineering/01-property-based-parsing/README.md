# 01 -- Property-Based Parsing

## Backstory

Somewhere upstream, a scraper is pulling product prices off a dozen
different retail sites. Some show `"$1,234.56"`. Some show `"USD 99.99"`.
A European site shows `"1.234,56 EUR"` -- same separators as US English,
swapped meaning. A refunds page shows `"-$5.00"`. Every one of these
strings eventually lands in the same downstream pipeline, and that
pipeline needs one typed `Price` out of every one of them, or a clean
error it can log and skip.

Someone already wrote that parser (`src/impl.py` in this task) and it is
correct. What it does NOT have is a test suite that would catch someone
breaking it six months from now -- a "quick fix" that drops the currency
symbol, an off-by-one in the separator logic that silently mis-parses
every European price, a refactor that swallows the error case and starts
returning `None`. This task is that test suite. You are not implementing
the parser -- you are the person whose job is to make sure nobody can
break it without a test going red.

## What's given

- `src/impl.py` -- the correct, complete parser. Read it. Its module
  docstring explains the separator-disambiguation rule and the currency
  rules in detail; the rest of the file is short. **Do not edit this
  file.**
- `src/sut.py` -- a generated shim. Your tests import from `src.sut`
  (`from src.sut import parse_price, format_price, Price, ParseError,
  KNOWN_CURRENCIES`), never from `src.impl` directly. This is what lets
  grading swap in a broken implementation behind your test's back without
  your test file changing at all.
- `tests/test_parser.py` -- an empty scaffold with TODO guidance in
  comments. This is where your suite goes.

## What's required

Write `tests/test_parser.py` using [Hypothesis](https://hypothesis.readthedocs.io/)
property-based tests (plus ordinary example-based tests where a specific
case is worth pinning down) that would catch a real regression in
`parse_price` / `format_price`. You are not told what the regressions
look like -- that is the point. Think about what must ALWAYS be true of a
correct price parser, regardless of which specific input you happen to
feed it, and write tests that check those invariants rather than tests
that check one hand-picked example.

Grading is NOT "does your suite pass" alone -- an empty test file also
"passes" (it just doesn't run anything, which is why there's a minimum
test count). Grading is mutant-killing: your suite is run once against
the correct implementation (it must fully pass, and must collect a
minimum number of tests) and then once against each of several buggy
variants of the parser, hidden from you. A buggy variant your suite still
passes against has "survived" -- exactly the situation you don't want in
a real regression six months from now.

## Completion criteria

From the module root (`16-testing-engineering/`):

```bash
uv run python 01-property-based-parsing/tests/validate.py
```

Prints `PASSED` (with a `killed N/N mutants` detail line) on success, or a
single `NOT PASSED: <reason>` line and a non-zero exit code otherwise --
including while `tests/test_parser.py` is still the empty stub.

## Estimated evenings

1-2

## Topics to read up on

- Property-based testing: what it is, how it differs from example-based
  testing
- Hypothesis strategies (`st.text`, `st.decimals`, `st.builds`,
  `st.sampled_from`, composing strategies)
- `assume()` and why it's different from just `if`-skipping inside a test
- Shrinking: what Hypothesis does when it finds a failing example, and how
  to read a shrunk counterexample
- Round-trip, idempotence, and metamorphic invariants as testing patterns
  (a metamorphic property relates two related inputs' outputs to each
  other, rather than checking one output against a fixed expected value)
- `decimal.Decimal` vs `float`, and why exact-value arithmetic matters for
  money

## Off-limits

`.authoring/` (at the module root) holds the mutant bank and the design
notes for this task -- it is the answer key. Don't open it before you're
done; the point of this task is to find the invariants yourself.
