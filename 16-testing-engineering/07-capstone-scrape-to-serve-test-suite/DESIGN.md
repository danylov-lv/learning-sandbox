# Test strategy memo -- scrape-to-serve catalog stack

Fill in every section below with your own writing (not placeholder text).
`tests/validate_cp3.py` checks that each `##` heading is present, has a
minimum amount of content, and does not still say things like `[fill in`
or `TODO`. Write in prose; a few sentences per section is enough as long
as it is genuinely yours.

## Testing pyramid for this stack

[fill in: how many tests do you have at each layer (unit/property,
integration, contract), and why that shape -- what would go wrong if the
pyramid were inverted for this particular stack?]

## What each layer catches

[fill in: for each of the three suites (unit, integration, contract),
name a concrete class of bug it catches that the *other* two suites
would miss. Ground this in mutants you actually saw survive at some
point while writing the suites, not a generic textbook answer.]

## Where mutation testing found gaps

[fill in: describe at least one mutant that survived your suite on an
earlier attempt, what that told you about a missing assertion, and what
you added to kill it.]

## How I'd extend this to CI

[fill in: what would running CP1/CP2/CP3 look like as CI jobs -- which
jobs need Docker, how would you keep the container-heavy jobs fast, and
what would you do differently for a real production version of this
stack (e.g. a nightly full mutation run vs. a fast per-PR check)?]
