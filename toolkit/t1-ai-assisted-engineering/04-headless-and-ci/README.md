# 04 -- Headless and CI

## Backstory

Every other task in this module runs Claude interactively. But a
CLAUDE.md, a subagent, and a hook all still assume a human (or Claude
itself) is driving turn by turn. `claude -p` drops that assumption: one
prompt in, one structured result out, no conversation. That's the
building block for wiring Claude into anything scripted -- a pre-commit
check, a scheduled job, or (the realistic version, here) a CI step that
only runs an AI review when someone explicitly asks for one by applying a
label to a PR, not on every push.

This task ships the actual pattern `ci-meta` (this repo's own CI module)
will later host for real: a label-triggered review step, not a
blanket one. Nobody wants an API call and a bot comment on every commit
to every branch.

## What's given

- `deliverable/scripts/ai-review.sh` -- stub script with the contract in
  its own comment header.
- `deliverable/.github/workflows/ai-review.yml` -- stub workflow with a
  deliberately wrong trigger (`push`) and a placeholder step, so it stays
  valid YAML while unfinished.
- `tests/validate.py` -- the validator; read it if you want to see
  exactly what's checked. No live `claude` call is required or made by
  the validator.
- `hints/` -- three levels of hints.

## What's required

1. Implement `ai-review.sh`: build a review prompt from `git diff`, call
   `claude -p` headless with `--output-format json` and a restricted
   `--allowedTools`, non-interactively.
2. Rewrite `ai-review.yml`: trigger on a pull-request LABEL (`types:
   [labeled]`), gate the actual review job/step on the specific label
   name via an `if:` condition, and add a step that installs and invokes
   Claude Code headless against the PR's diff.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t1-ai-assisted-engineering
uv run python 04-headless-and-ci/tests/validate.py
```

It checks, in order:

- `ai-review.sh` invokes `claude` only with `-p`/`--print` (never bare),
  references `--output-format` and `git diff`, and has no interactive
  `read` prompt.
- `ai-review.yml` parses as YAML, triggers on `pull_request` with
  `types: [labeled]` (not on `push`), has a job/step `if:` condition
  naming a specific label, and has a step that invokes `claude` headless
  (or a claude-code GitHub Action).

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- Claude Code headless mode: `-p`/`--print`, `--output-format`
  (text/json/stream-json), and `--allowedTools` permission syntax
- GitHub Actions trigger shapes: `pull_request` vs `pull_request_target`,
  the `types:` filter, and `if:` conditions using the `github.event`
  context
- Why label-gated automation (vs. "run on every push") matters for cost
  and signal-to-noise in CI
- YAML 1.1's boolean-keyword key resolution (`on`, `yes`, `no`, `off`)
  and why it bites GitHub Actions workflows specifically when parsed by
  a generic YAML library

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract across all six tasks -- spoilers, in general. Read it after
finishing this task, if at all.
