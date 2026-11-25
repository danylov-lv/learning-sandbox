Don't start by trying to guess what the hidden bugs might be -- you can't
see them, and trying to guess wastes effort chasing the wrong thing.
Instead, start from the parser's own contract: what does `src/impl.py`'s
module docstring promise is always true, no matter what specific string
you feed it? A promise made about "any input", not "this one example
input", is exactly the shape of thing property-based testing is good at
checking.

There are at least three separate kinds of promise being made in that
docstring: a promise about what comes back on GOOD input, a promise about
what happens on BAD input, and a promise about how two DIFFERENT-LOOKING
good inputs relate to each other. Each of those wants a different test,
and a suite that only covers one of the three would still let a lot of
real regressions through.

Also: a handful of concrete example tests (not `@given`-decorated, just
plain `assert parse_price(...) == ...`) are not a cop-out here. Hypothesis
searches randomly; it is not guaranteed to happen to generate the exact
European-format string or the exact negative-amount string you read about
in the docstring. If a specific input format matters to you, say so
explicitly with a plain example test, in addition to your property tests.
