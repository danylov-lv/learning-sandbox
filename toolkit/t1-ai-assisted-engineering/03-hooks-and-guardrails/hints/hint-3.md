No ready-made hook code here -- just the exact contract the validator
checks, so you can verify your own script by hand before running
`validate.py`.

Try this yourself, from `deliverable/`, against the shipped fixtures at
`../tests/fixtures/`:

```bash
cd deliverable
CLAUDE_PROJECT_DIR="../tests/fixtures/tests-passing" \
  python .claude/hooks/run-tests.py <<< '{"cwd": "../tests/fixtures/tests-passing"}'
echo "exit: $?"
```

Against `tests-passing`, this must exit `0` and print nothing (or
something that doesn't parse as `{"decision": "block", ...}`). Swap in
`tests-failing` and it must either exit non-zero OR print exactly
`{"decision": "block", "reason": "..."}` to stdout (still fine to exit 0
in that case -- the JSON is what the validator looks for first).

Do the same for `lint.py` against `../tests/fixtures/lint-clean` and
`../tests/fixtures/lint-dirty`.

If your script raises an uncaught exception instead of handling the
subprocess result, that will also produce a non-zero exit code -- which
happens to "pass" the failing-fixture check by accident but fails the
passing-fixture check for real, since a crash isn't conditional on the
fixture. Both directions have to work for the validator to accept it.
