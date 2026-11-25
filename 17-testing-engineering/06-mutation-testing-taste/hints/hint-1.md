Don't start by staring at `target.py` guessing what might be undertested.
Start by actually running the tool: build the `cosmic-ray` config, run
`baseline`, `init`, `exec`, `dump` (the README has the exact commands, or
just run `tests/validate.py` and read what it prints). It will hand you a
list of surviving mutants -- read that list before you write a single new
test.

Each survivor names an `operator_name` (e.g.
`core/ReplaceComparisonOperator_Lt_LtE`) and, in the raw `dump` output, a
line/column position in `target.py`. That tells you exactly which
comparison, boundary, or branch in the source was changed and your suite
still passed anyway -- which means nothing you asserted actually depended
on that piece of logic being correct. The fix is never "add another call
to the happy path"; it's "find the one input that would come out
differently if this specific mutation were real, and assert on it."
