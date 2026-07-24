# ci-meta

GitHub Actions CI for the sandbox repository itself.

## What this is

Every other module in this repo ships an **unsolved** learner exercise:
`raise NotImplementedError`, `todo!`/`unimplemented!`, or the string
`not implemented`, with no reference solution committed anywhere. `ci-meta`
is the one exception. It is committed, working **repository
infrastructure** — the same category as each module's `generate.py` or
`harness/` — not a graded task. There is no stub here to solve, so it
ships complete, and its own validator (`ci-meta/tests/validate.py`)
passes on stock, unlike every other module's.

## The central insight

Because every task validator in this repo fails by design against an
unsolved stub, CI cannot assert **"the tasks pass."** That check would be
permanently red from the day a module is generated until a human sits
down and solves it — which may be never, since solving is the learner's
job, not CI's.

So CI asserts something different and genuinely checkable: the
**authoring contract** — the exact set of invariants each module's own
generation process verified by hand when it was written:

1. required scaffold files are present (`README.md`, `hints/hint-{1,2,3}.md`,
   `NOTES.md`, the module's lock/manifest file);
2. no reference solution has leaked (learner stubs still contain their
   marker, deliverable doc templates are still unfilled, no `solution.*`
   is tracked);
3. python dependency locks are valid (`uv lock --check`);
4. for lightweight service modules, the module's own `docker-compose.yml`
   services actually boot and reach healthy.

This is a real, living progress check. It catches leaked solutions,
lock files that drifted out of sync with `pyproject.toml`, validators that
crash with a raw traceback instead of failing cleanly, tracked junk that
should have been gitignored, and service definitions that no longer boot
— all without ever needing a module's tasks to be solved.

## Architecture

```
push / pull_request / workflow_dispatch
            |
            v
        detect  ──────────────────────────────► outputs: modules (JSON array), any (bool)
            |
            | needs: detect, if: any == 'true'
            v
        verify (matrix: one job per changed module)
            |
            runs ci-meta/run_module_ci.py <module-id> for each

        guards  (independent job, always runs)
            |
            runs ci-meta/repo_guards.py
```

- **detect** (`ci-meta/detect_changes.py`) diffs the push/PR against a base
  ref and maps changed files to registry module ids.
- **verify** fans out into a matrix job per changed module and runs
  `ci-meta/run_module_ci.py <module-id>`, which checks that module's
  authoring contract.
- **guards** (`ci-meta/repo_guards.py`) runs unconditionally on every push
  and PR, independent of what changed, and checks repo-wide invariants.

## The registry (`ci-meta/registry.py`)

Single source of truth: one `Module` row per module id, giving its
repo-relative `path`, `kind` (`python` / `rust` / `pnpm` — which
lock/manifest file and stub marker apply), `services` classification, and
a short `note`.

Service classification:

| Class | Meaning | Modules |
|---|---|---|
| `light` | Own `docker-compose.yml` with only Postgres/Redis/Mongo. CI brings it up with `--wait` to prove the containers actually boot and reach healthy. | 01, 03, 10, 12 |
| `heavy` | Has a compose file, but it's too big or too special for a hosted GitHub runner (Spark, Airflow, ClickHouse, redpanda, Debezium, MinIO, a GPU-bound Ollama, multi-GB seeded data). CI runs only the static checks and emits an `::notice::` explaining why the live step is skipped — honestly, not silently. | 02, 04, 05, 06, 07, 08, 09, 13, 15 |
| `none` | No compose file; static checks only. | 11, 14, 16, 17, 18, 19, 20, and all four `toolkit/` modules |

The honest reason `heavy` modules don't run live in CI: a hosted runner
has 2 vCPU / 7 GB RAM and no GPU, and several of these stacks (a Spark
cluster, ClickHouse at the 50M-row scale the module actually exercises,
Ollama on a GPU) either won't fit or would produce a boot check so
degenerate (an empty container with none of the seeded scale that makes
the module's tasks meaningful) that it wouldn't prove anything real. Module
20's `kind` cluster and modules 16/18/19's ephemeral/testcontainers-managed
services are structurally different from `docker-compose.yml` and are
`none` for that reason, not because they're unimportant.

## Change detection (`ci-meta/detect_changes.py`)

Base ref selection:

- `pull_request` event → `origin/$GITHUB_BASE_REF`
- `push` event → `$GITHUB_EVENT_BEFORE` (falls back to `HEAD~1` if unset or
  all-zeros — e.g. the first push of a new branch)
- anything else (local run, `workflow_dispatch`) → `HEAD~1`

`git diff --name-only <base>...HEAD` produces the changed file list (with
a graceful fallback to `git diff --name-only HEAD~1` if the base ref
can't be resolved, e.g. a shallow local clone). Each changed path is
mapped to the registry module whose `path` is the **longest** matching
directory prefix — this is what makes `toolkit/t3-cli-data-toolkit/...`
resolve to that toolkit module rather than being swallowed by a shorter,
wrong prefix. Files outside every registered module path (root docs,
`.github/`, `ci-meta/` itself) do not add anything to the matrix —
`guards` already covers repo-wide concerns. Matches are deduped and
returned in registry order.

## Running it locally

```bash
python ci-meta/detect_changes.py
python ci-meta/run_module_ci.py 01-sql-foundations
python ci-meta/repo_guards.py
python ci-meta/tests/validate.py
```

`detect_changes.py` run locally diffs against `HEAD~1` and prints the
resulting JSON module array plus a readable list to stdout instead of
writing to `$GITHUB_OUTPUT`.

`run_module_ci.py` is safe to run without `uv` or `docker` installed: it
detects their absence, emits an `::notice::` explaining what would have
run in CI, and still exercises every static check.

## Extending it

Adding module 21 (or a fifth toolkit module) is a one-line change: add a
`Module(...)` row to `MODULES` in `ci-meta/registry.py` with its path,
kind, and service classification. Nothing else in `ci-meta` needs to
change — `detect_changes.py`, `run_module_ci.py`, and `repo_guards.py` all
read the registry, they don't hardcode a module list.
