# Design rationale + live verification notes (ci-meta)

## The central insight, restated

Every other module in this repo ships an unsolved stub with no reference
solution anywhere. That means every task validator fails by design, from
the moment a module is generated until a human solves it -- which may be
never. CI therefore cannot assert "the tasks pass": that assertion would
be permanently red. What it *can* assert, and what it does assert, is the
**authoring contract** each module's own generation process already
verified by hand: scaffold files present, no solution leaked, lock files
valid, and (for lightweight service modules) the service containers
actually boot. This is why `ci-meta/tests/validate.py` is the one
validator in the repo that is *expected* to pass on stock -- ci-meta
itself has no stub, it ships complete, as infrastructure.

## Design decisions and why

- **Registry as single source of truth.** `registry.py` is a plain dict of
  `Module` rows (path/kind/services/note). Every other script imports it
  rather than hardcoding a module list, so adding module 21 later is a
  one-line change (see the README's "Extending it" section).
- **Longest-prefix-match for change detection**, not simple substring
  containment, so `toolkit/t3-cli-data-toolkit/...` resolves to that
  toolkit module rather than being swallowed by a shorter wrong prefix
  (there is no shorter prefix collision in this registry today, but the
  logic is written to be correct if one is ever added).
- **`run_module_ci.py` never runs a module's own task validators.** Only
  `checks.py`'s structural checks and `uv lock --check` run. Running the
  real per-task validators would just reproduce the "everything is
  perpetually red" problem this design exists to avoid.
- **Light vs. heavy is a hard split, not a spectrum.** Only 01, 03, 10, 12
  have a `docker-compose.yml` whose entire service list is
  Postgres/Redis/Mongo with a real healthcheck -- confirmed by reading
  every module's `docker-compose.yml` directly before classifying it.
  Everything else with a compose file (02, 04-09, 13, 15) either needs
  more than a hosted GitHub runner's 2 vCPU / 7 GB RAM (a Spark cluster,
  ClickHouse at the 50M-row scale the module actually tests, a GPU for
  Ollama) or a boot check on an empty container would prove nothing about
  the module's actual scenario (02's tuned Postgres is otherwise identical
  in shape to 01/03's -- it's the *seeded scale and bloat scenario* that
  makes it heavy, not the container itself).

## What was actually verified locally, live

This machine has both `uv` and Docker Desktop available, and `postgres:16`
was already pulled locally, so the light-module path was verified as a
real container boot, not just a code-reading exercise:

- **`python ci-meta/tests/validate.py`** -- `PASSED`. Confirmed all five
  ci-meta scripts import cleanly, the registry matches the real module
  directories on disk (24 modules: 01-20 plus the four toolkit modules),
  every registered path exists, `detect_changes.map_files_to_modules`
  correctly resolves the sample cases (including the toolkit
  longest-prefix case and an unmatched root file), and the workflow file
  references `detect_changes.py`/`run_module_ci.py`/`repo_guards.py`/
  `fromJSON(needs.detect.outputs.modules)`.
- **`python ci-meta/repo_guards.py`** -- fails with exactly one reason:
  `GENERATION_STATE.md has pending items, e.g. line 32: - [ ] ci-meta --
  pending (stub README only)`. That is expected and will clear once the
  orchestrator marks ci-meta done in `GENERATION_STATE.md` (not touched by
  this generation, per instructions). The junk-file guard and the
  registry-matches-disk guard both pass.
- **`python ci-meta/detect_changes.py`** (local run, diffs `HEAD~1`) --
  printed `["toolkit/t1-ai-assisted-engineering",
  "toolkit/t2-modern-python-toolchain", "toolkit/t3-cli-data-toolkit",
  "toolkit/t4-git-advanced"]`, matching the previous commit
  (`feat: add toolkit track (t1-t4)`) exactly.
- **`python ci-meta/run_module_ci.py 17-system-design`** (a `none`-services
  module) -- `PASSED`, static checks only, no docker involved.
- **`python ci-meta/run_module_ci.py 01-sql-foundations`** (a `light`
  module, docker actually available) -- `PASSED`. `docker compose -f
  01-sql-foundations/docker-compose.yml up -d --wait` really brought up
  the `postgres:16` container and waited for its healthcheck
  (`pg_isready`) to report healthy, then `down -v` really tore it down --
  confirmed with `docker volume ls` afterward showing no
  `01-sql-foundations_sandbox_01_pgdata` volume left behind.
- **Docker-absent fallback**, exercised by monkeypatching
  `shutil.which("docker")` to return `None` in a throwaway interpreter
  session: `run_module_ci.run("01-sql-foundations")` returned `(True,
  "ok")` and emitted `::notice::docker not available locally; skipping
  live service boot ...` instead of attempting the compose call --
  confirms the module is smoke-runnable on a machine without Docker.
- **`run_module_ci.py 02-sql-optimization`** (a `heavy` module) -- `PASSED`
  with `::notice::live service tests skipped for 02-sql-optimization:
  <registry note>`, no live compose call attempted.
- **Bad module id** -- `run_module_ci.py 99-does-not-exist` failed cleanly
  with `NOT PASSED: "no such module in registry: '99-does-not-exist'"`,
  no traceback.
- **stdlib-only**, confirmed by AST-parsing every import statement in
  `registry.py`, `checks.py`, `detect_changes.py`, `repo_guards.py`, and
  `tests/validate.py`: nothing outside the standard library, except an
  optional `yaml` import in `tests/validate.py` guarded by `try/except
  ImportError` (per the task spec's own instruction to parse the workflow
  YAML "if importable, else do robust string/regex assertions" -- the
  ambient interpreter here has no `pyyaml` installed, so the fallback path
  is what actually ran and passed).
- **`git add -n` / `git status --porcelain`** over `ci-meta` and `.github`
  -- only the intended new files staged (`registry.py`, `checks.py`,
  `detect_changes.py`, `run_module_ci.py`, `repo_guards.py`,
  `tests/validate.py`, the updated `README.md`, and
  `.github/workflows/ci.yml`). No `__pycache__`, `.venv`, or other junk
  would be staged.

## What could NOT be verified from here

The workflow file (`.github/workflows/ci.yml`) was statically validated
only -- its YAML structure, job graph, `needs`/`if`/`strategy.matrix`
wiring, and the exact strings the tests/validate.py check for
(`fromJSON(needs.detect.outputs.modules)`, the three script paths) were
all confirmed, and `run_module_ci.py`'s logic was exercised directly
(bypassing the workflow) against a real changed module with a real
Docker daemon. But this machine cannot actually dispatch a GitHub Actions
run: the `verify` job's matrix fan-out, the `detect` job's `$GITHUB_OUTPUT`
plumbing under a real `pull_request`/`push` event (as opposed to the
locally-simulated `HEAD~1` fallback path), and `astral-sh/setup-uv@v6`'s
actual behavior on a hosted `ubuntu-latest` runner were not and cannot be
exercised from this session. This is a structural limitation of live-
verifying CI infra without pushing to GitHub, not a gap in the checks
above.

## Two real bugs found and fixed during authoring (not left in)

1. **Case-insensitive filename matching on Windows collided two unrelated
   files.** The first draft of `checks.check_no_solution` used
   `Path.rglob("DESIGN.md")` to find deliverable-doc templates.
   `Path.rglob` on Windows is case-insensitive, so it also matched
   `<module>/.authoring/design.md` (a lowercase, deliberately-filled
   authoring-notes file, the opposite of an unfilled template) and flagged
   every module with a `.authoring/design.md` as "solution leaked."
   Rewrote to an explicit `os.walk` + exact case-sensitive filename
   comparison, independent of host filesystem case-sensitivity.
2. **The stub-marker check was far too strict for `python`-kind modules.**
   The repo's 18 python-kind modules use wildly different task-deliverable
   shapes -- raw `.sql` files (01, 02), shell `solve.sh` scripts (t3), a
   "fix this real broken config" task with no textual marker at all (t2),
   an inverted testing module where the given code is complete and the
   learner-authored file is a comment-only instructional stub (16), git
   repository state with no source files at all (t4) -- none of these use
   `NotImplementedError` as their unsolved-marker convention, even though
   the module kind is `python`. Verified this by grepping every one of
   these modules directly (excluding `.venv`) and confirming zero
   legitimate matches. Rust (18) and TypeScript (19) are single,
   homogeneous task shapes with a confirmed-consistent marker in every
   task (`todo!`/`unimplemented!`, `not implemented`), so the marker check
   stayed a hard failure for those two kinds; for `python` it is now
   informational/best-effort only, per the task spec's own "skip
   gracefully if a module legitimately has no such tree" instruction.

Also found and excluded one legitimate `target/` collision in
`repo_guards.check_no_tracked_junk`: `13-scraping-at-scale/docker/target/`
is the mock target site's Docker build context (a directory legitimately
named `target`), not a Rust build-artifact directory. Excluded by exact
path prefix with a code comment explaining why, rather than weakening the
general `target/` junk pattern that exists to catch an accidentally
committed Rust `target/` directory.
