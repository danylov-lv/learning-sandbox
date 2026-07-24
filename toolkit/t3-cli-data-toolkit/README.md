# t3 — CLI Data Toolkit

## What this module covers

Five single-evening drills in using CLI data tools well, not just knowing
they exist: `jq` for real transformations (not just filtering), `rg` +
`fd` fluency, the `duckdb` CLI as a zero-server swiss knife over
Parquet + CSV, honest micro-benchmarking with `hyperfine`, and batch
processing with GNU `parallel`. No docker, no capstone — this track is
"dip in anytime."

Every task is a realistic "explore/fix data from the terminal" scenario
against generated fixtures under `data/` (gitignored, produced by
`generate.py`). Every task's validator is an **expected-output check**:
it runs your script, then compares what it printed or wrote against a
ground truth the validator computes independently — in Python, from the
same source files, never by re-running your own command with different
flags and trusting agreement.

## Setup

```bash
cd toolkit/t3-cli-data-toolkit
uv sync
uv run python generate.py
```

`generate.py` is deterministic (fixed seed) — re-running it reproduces
byte-identical fixtures. It respects a `SCALE` env var (default `1.0`) if
you want a larger tree, but the default is already sized to keep
`data/` in the low hundreds of KB.

Tools required on `PATH`: `jq` (1.8+), `rg` (15+), `fd` (10+), `duckdb`
CLI (1.5+), `hyperfine` (1.20+), GNU `parallel`. None of these are
Python packages — install them with your platform's package manager
(scoop/choco on Windows, brew on macOS, apt on Linux) before starting.

## How to run a validator

Validators run **from the module root**, always:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python 01-jq-nested-json/tests/validate.py
```

Every validator prints exactly one line and exits: `PASSED` on success,
or `NOT PASSED: <reason>` naming what's missing or wrong. No raw
tracebacks.

## Windows / Git Bash notes

These come up in specific tasks (also called out in their own READMEs),
collected here so you only have to learn them once:

- `duckdb`'s CLI is a native Windows binary — it does not understand a
  POSIX-style path like `/d/Programming/...`. If you build a path with
  `` `pwd` `` inside a bash script, use `` `pwd -W` `` instead so DuckDB
  gets a `D:/...`-style path.
- `hyperfine` runs each benchmarked command through the platform's
  default shell — `cmd.exe` on Windows, not bash — so a single-quoted
  glob like `'*.log'` won't survive; use double quotes.
- GNU `parallel` prints a one-time "Finding the maximal command line
  length" notice (and may nag about citing) to **stderr** on first use
  on a machine. It doesn't affect stdout or the joblog; pass
  `--will-cite` if you want it gone entirely.

## Tasks

| # | Task | Tool(s) | Evenings |
|---|------|---------|:---:|
| 01 | jq-nested-json | `jq` | 1 |
| 02 | ripgrep-and-fd | `rg`, `fd` | 1 |
| 03 | duckdb-cli-swiss-knife | `duckdb` | 1 |
| 04 | hyperfine-benchmark | `hyperfine`, `fd`, `rg` | 1 |
| 05 | gnu-parallel-batch | `parallel`, `jq` | 1 |

Total: 5 evenings. No prescribed order within this module — each task is
independent of the others' deliverables (though 04 reuses 02's file tree,
and 05 revisits the reshape skill from 01, on different fixtures).

- **01** — flatten nested pages of scraped listings, join in a source's
  tier by key, group by category, and reshape into a new object — pure
  `jq`, no filtering-only shortcuts.
- **02** — four independent drills: a regex capture group, an `fd` glob
  excluding a directory, a lookaround-style pattern (`rg -P`), and a
  file census by extension.
- **03** — three `duckdb -json -c "..."` one-liners straight against a
  Parquet directory and a CSV: a hive-partitioned aggregate, a CSV join,
  and a `LAG()` window function.
- **04** — benchmark two ways of counting the same thing with
  `hyperfine`, honestly: warmup runs, `--export-json`, and a *relative*
  winner recorded in `ANSWER.md` — never an absolute-millisecond claim.
- **05** — fan a per-file `jq` transform across 30 input files with GNU
  `parallel`, bounded by `--jobs`, with a `--joblog` proving what ran.

## `.authoring/` is off-limits until after a task

`.authoring/design.md` documents the grading contract (exact expected
answers, ground-truth formulas) for this module's task-authoring work. It
is not a solution file — there are no reference solutions anywhere in
this repository — but read it after finishing a task, if at all, same
rule as every other module.
