# 06 -- Mutation Testing Taste

## Backstory

A pricing calculator shipped with a green test suite and 100% line
coverage. Every function got called at least once, every line executed,
the CI badge was green. Then a one-character change to the discount
formula -- `pct / 100` became `pct // 100` -- went out in a refactor, and
nobody noticed until a customer got charged full price for a "discounted"
order. The test suite still passed. It had called the function; it had
just never checked the number that came back closely enough to notice it
was wrong.

Line coverage answers "did this code run during the tests?" It says
nothing about whether the tests actually ASSERT the behavior that code is
supposed to have. Mutation testing answers a sharper question: take the
correct program, introduce one small, mechanical bug (a mutant) -- flip a
comparison, swap `+` for `-`, change a boundary -- and ask whether the test
suite notices. A suite that kills every mutant is a suite that would have
caught the `pct // 100` bug. A suite that lets mutants survive has holes,
and the surviving mutants tell you exactly where.

Every other task in this module hides a mutant bank behind the scenes and
grades your tests by whether they kill it. This task is different: you run
the REAL tool yourself (`cosmic-ray`), read its own survivor report, and
strengthen the suite until nothing survives. This is the actual, everyday
workflow of using a mutation tester -- not a simulation of it.

## What's given

- `src/target.py` -- a small, CORRECT pricing/shipping module: read it, do
  not edit it. Four functions, each with real branches and boundaries:
  - `apply_discount(price, pct, *, min_price)` -- percentage discount,
    floored at a minimum price, with input validation.
  - `classify_price_tier(price)` -- buckets a price into
    `"budget"` / `"standard"` / `"premium"` / `"luxury"`.
  - `is_valid_sku(sku)` -- validates a `"ABC-1234"`-shaped product code
    (3 uppercase letters, a hyphen, 4-6 digits).
  - `shipping_cost(weight_kg, *, distance_km, express=False)` -- a
    weight/distance shipping formula with an express multiplier and a
    minimum charge.

  Unlike the other tasks in this module, there is no `src/sut.py` shim
  here -- `cosmic-ray` mutates `target.py` in place (on a scratch copy) for
  each trial, so tests import it directly: `from target import ...`.

- `tests/test_target.py` -- a WEAK-BUT-GREEN starting suite. It passes
  against `target.py` right now, but it only exercises one happy-path call
  per function -- no boundaries, no error paths, no branches that return
  something other than the obvious case. This is your starting point, not
  a stub -- run it, watch it pass, then go find out how little that
  proves.

- `cosmic-ray` is already installed in this module's environment
  (`uv sync` in the module root pulled it in).

## What's required

Edit `tests/test_target.py` -- add test cases (you may also edit the
existing ones) until running `cosmic-ray` against `target.py` reports ZERO
surviving mutants. You are not editing `target.py`; it is already correct.

This means, for each function, actually testing:

- Every boundary value named in its docstring (the exact price where a
  tier flips, the exact digit count where a SKU becomes valid/invalid, the
  exact weight/distance where an error is raised).
- The error paths (`ValueError` for out-of-range inputs), not just the
  happy path.
- Both sides of every `if`/`or` branch, with a value that would produce a
  DIFFERENT result if that branch's logic were subtly wrong -- not just
  "doesn't crash."

## How to run cosmic-ray yourself

`tests/validate.py` runs this exact sequence for you and reports
`PASSED`/`NOT PASSED`, but you should also know how to drive `cosmic-ray`
by hand -- that hands-on loop (run it, read the survivor list, write a
test, run it again) is the actual point of this task.

```bash
# from the module root (16-testing-engineering), in a scratch directory
# containing both target.py and test_target.py side by side:

python -m cosmic_ray.cli new-config cr.toml     # or hand-write one, see below
python -m cosmic_ray.cli baseline cr.toml        # sanity check: unmutated code must pass
python -m cosmic_ray.cli init cr.toml session.sqlite
python -m cosmic_ray.cli exec cr.toml session.sqlite
python -m cosmic_ray.cli dump session.sqlite     # JSON-lines: [WorkItem, WorkResult] per mutant
```

**Windows gotcha, load-bearing**: `cosmic-ray`'s config has a
`test-command` string that it runs as a raw shell command per mutant. If
you write `test-command = "python -m pytest test_target.py -q"`, the bare
`python` on your `PATH` can resolve to a *different* interpreter than this
project's `.venv` -- one without `pytest` installed. When that happens,
every single mutant (and even the unmutated baseline) gets reported as
"killed," because the test command itself failed to run at all, not
because a test failed. The tell is `cosmic-ray dump` showing `"output":
""` on every job. Always build `test-command` from `sys.executable`, e.g.:

```python
import sys
py = sys.executable.replace("\\", "/")
test_command = f'"{py}" -m pytest test_target.py -q'
```

**Also always run `cosmic-ray baseline` before `init`/`exec`.** If the
baseline itself fails, something about the test command is broken (see
above) -- fix that before trusting anything `exec` reports.

`tests/validate.py` does exactly this, in a temporary working copy (so
your repo doesn't collect `session.sqlite` files and generated configs),
and prints the surviving mutants' `operator_name`s directly -- reading
that list, and matching each name back to a branch in `target.py` you
haven't tested, is deliberately most of the exercise. `cosmic-ray`'s
`core/ReplaceComparisonOperator_*_Is` / `*_IsNot` operators are excluded
from the count `validate.py` grades on (see "A note on equivalent
mutants" below) -- everything else must be killed.

## Completion criteria

From the module root:

```bash
uv run python 06-mutation-testing-taste/tests/validate.py
```

Prints `PASSED` once `cosmic-ray` reports zero surviving mutants (other
than the excluded identity-comparison operators). On survivors, prints
`NOT PASSED` naming the surviving `operator_name`s so you know where to
look next -- this is safe to show, unlike the other tasks' mutant banks:
reading real survivor output is the whole point here.

## A note on equivalent mutants

Not every mutant a tool generates is meaningfully killable. `cosmic-ray`
includes operators like `ReplaceComparisonOperator_Lt_Is`, which rewrites
e.g. `x < lo` into `x is lo`. For small integers, CPython caches and
interns every value from -5 to 256 as a shared singleton object, so `x is
N` and `x == N` can end up behaviorally indistinguishable for a
mutation that was never semantically about equality to begin with -- no
test you write changes the outcome, because the "bug" isn't actually
observable. This is a genuine equivalent mutant, not a gap in your tests.
`tests/validate.py` filters `core/ReplaceComparisonOperator_*_Is` and
`*_IsNot` operators out of what it grades for exactly this reason. If you
run `cosmic-ray` by hand and see one of those in the raw `dump` output,
that is expected and not something to chase.

## Estimated evenings

1-2

## Topics to read up on

- Mutation testing: what a "mutant" is, and the operator-based approach
  (systematically rewriting operators, constants, and comparisons) most
  mutation tools use to generate them
- Mutation score (killed / total mutants) as a measure of test suite
  quality, and why it is a stronger signal than line or branch coverage
- Surviving vs. killed mutants, and how to read a survivor back to the
  specific assertion your suite is missing
- Equivalent mutants: mutations that cannot be distinguished from the
  original program by any test, and why 100% mutation score is sometimes
  not the right target for every single reported mutant
- `cosmic-ray`'s operator catalog (`python -m cosmic_ray.cli operators`)
  and its `init` / `exec` / `dump` session workflow

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API
contract and this module's verification philosophy -- spoilers, in
general. This particular task has no hidden mutant bank to spoil (the
real tool generates its own mutants), but the file also documents the
Windows `cosmic-ray` gotcha and the equivalent-mutant caveat above in more
detail than this README -- reading it after finishing is fine either way.
