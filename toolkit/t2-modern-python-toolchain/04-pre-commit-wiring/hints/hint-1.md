# Hint 1

Look at `fixtures/bad/statkit/stats.py` and `fixtures/clean/statkit/stats.py`
side by side (`diff` them, or just read both). Every difference between
the two is something one specific hook exists to catch. Count the
differences — that tells you how many hooks you actually need, which
should match what the README lists.

pre-commit's own docs list its config schema and a starter
`.pre-commit-config.yaml` you can adapt — `pre-commit sample-config`
prints one.
