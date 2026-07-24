# 01 — uv Project Management

## Backstory

A teammate hands you `pricetool` — a five-line internal CLI someone wrote
in an afternoon to print a quick min/max/avg summary of a hardcoded price
list. It "works on their machine" because they have a stray global
install of PyYAML lying around and they always type
`python -m pricetool.cli` from inside the `src/` folder out of habit.
Nobody else can run it. Your job: turn it into a real uv-managed project —
correct declared dependencies, a working console command, a dev
dependency group so `pytest` is available without polluting the runtime
install, and a demonstration that it also works the way a *published*
internal tool would be consumed — via `uv tool run` (the mechanism behind
`uvx`), not just `uv run` inside its own checkout.

## What's given

- `project/src/pricetool/` — the CLI's source, complete and already
  correct. You will not edit any `.py` file in this task.
  - `data.py` — a fixed fixture: 5 prices and a small embedded YAML config
    string (`currency: USD`).
  - `cli.py` — `main()` parses the config with PyYAML and prints one
    summary line.
- `project/tests/test_cli.py` — a small given pytest suite for the CLI.
  It only runs at all once `pytest` is installed via the correct
  dependency group.
- `project/pyproject.toml` — **broken**: no dependencies declared (the
  code imports `yaml`, which isn't there), no `[project.scripts]` entry
  point, no dev dependency group. `[build-system]` is already filled in
  correctly — packaging depth is not this task's focus (see task 05 for
  that).
- `tests/validate.py` — the validator.
- `hints/` — three levels of hints.

## What's required

Fix `project/pyproject.toml` only:

1. Add the missing runtime dependency the code actually imports (PyYAML).
2. Add a `[project.scripts]` entry point named exactly `pricetool`,
   pointing at `pricetool.cli:main`.
3. Add a `dev` dependency group (PEP 735 `[dependency-groups]`) containing
   `pytest`.
4. Run `uv sync` inside `project/` and let it generate `project/uv.lock`
   (not committed — it's your output, not a given file).
5. Confirm the tool also runs the way a colleague installing it
   standalone would run it — without a checked-out venv of their own —
   using `uv tool run --from . pricetool` (the flag-explicit form of what
   `uvx` does under the hood). This exercises `uv`'s *tool* management
   path, not just its *project* management path, against the exact same
   entry point you just wired up.

Do not touch any `.py` file under `project/src` or `project/tests` —
the task is entirely in `pyproject.toml`.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t2-modern-python-toolchain
uv run python 01-uv-project-management/tests/validate.py
```

It checks, in order:

- `project/pyproject.toml` declares the `pyyaml` dependency, the
  `pricetool` console script mapped to `pricetool.cli:main`, and a `dev`
  dependency group containing `pytest` — parsed straight from the TOML.
- `uv sync` succeeds inside `project/` and produces `project/uv.lock`.
- `uv lock --check` confirms the lockfile is consistent with
  `pyproject.toml`.
- `uv run pricetool` prints the expected summary line.
- `uv run pytest -q` passes (proves the dev group actually resolves and
  installs).
- `uv tool run --from . pricetool` prints the same summary line, run as an
  ephemeral tool install rather than through the project's own venv.

Prints `PASSED` or `NOT PASSED: <reason>` and exits accordingly.

## Estimated evenings

1

## Topics to read up on

- uv project workflows: `uv sync`, `uv run`, `uv lock`
- `pyproject.toml` `[project.dependencies]` vs `[dependency-groups]`
  (PEP 735) vs the older `[tool.uv.dev-dependencies]`
- Console entry points (`[project.scripts]`) and how a build backend turns
  them into an installed command
- `uv tool install` / `uv tool run` / `uvx` and how they differ from
  `uv run` inside a project checkout
- Lockfile consistency checks (`uv lock --check` vs `uv sync --frozen`)

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
