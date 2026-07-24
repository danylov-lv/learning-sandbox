No ready-made script or workflow here — just the exact shapes the
validator checks.

**`ai-review.sh` must, somewhere in the file:**
- invoke `claude` with `-p` (or `--print`) on every invocation — no bare
  `claude` call anywhere, even a leftover debug one
- reference `--output-format`
- reference `git diff` literally
- not contain a `read ...` line (that's the interactive-input builtin —
  this script takes its input from `git diff` and an optional `$1`, never
  from a prompt)

**`ai-review.yml` must parse as YAML and have:**

```yaml
on:
  pull_request:
    types: [labeled]        # NOT triggered by push, NOT the full default type list
```

...one step somewhere under `jobs.*.steps` whose `run:` contains both
`claude` and `-p` (or a `uses:` referencing a claude-code GitHub Action,
if you'd rather use that instead of installing the CLI by hand) — and a
job- or step-level `if:` whose text contains the word "label" (the
validator checks for that substring specifically, case-insensitively, as
a proxy for "this actually checks which label fired the event," e.g.
`if: github.event.label.name == 'ai-review'`).

One real gotcha, worth knowing regardless of this task: PyYAML (and a lot
of other YAML 1.1 parsers) read an unquoted `on:` key in a GitHub Actions
workflow as the boolean `True`, not the string `"on"`. This validator
already accounts for it (`workflow.get("on", workflow.get(True))`) so you
don't need to work around it in your YAML — just know it's there if you
ever parse a workflow file yourself outside this task.
