# Hint 1

Run `pytest -q` inside `project/` right now, before changing anything.
Two tests fail — read both failures carefully, they're telling you
exactly what's wrong at runtime, independent of what mypy will later
tell you about the types. Then run `mypy --strict src` (yes, pass the
flag directly this time) and compare what it flags against what you
already suspected from the test failures.
