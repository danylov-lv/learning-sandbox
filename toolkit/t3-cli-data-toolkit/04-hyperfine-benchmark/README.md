# 04 — Honest Micro-Benchmarking with hyperfine

## Backstory

Two tools can both answer "how many `.log` files are under this tree?" —
`fd` filtering by extension, and `rg` listing files by glob. Which one is
actually faster is an empirical question, not a vibe, and answering it
honestly means more than running each command once and eyeballing the
clock: warmup runs so the OS file cache is primed for both equally,
enough repetitions to see the noise, and a comparison expressed
*relative* to each other — not as absolute milliseconds nobody else's
machine will reproduce.

## What's given

- `data/filetree/` — the same generated file tree task 02 uses (about a
  dozen `.log` files among a couple hundred other files).
- `src/benchmark.sh` — a stub that currently just exits 1. Fill it in
  with one `hyperfine` invocation comparing exactly two commands.
- `ANSWER.md` — a template with the sections you must fill in after
  reading your own exported results.
- `tests/validate.py` — the validator.
- `hints/` — three tiers of hints.

Run `uv run python generate.py` from the module root first if `data/`
doesn't exist yet.

**Windows/Git Bash note**: `hyperfine` runs each benchmarked command
through the platform's default shell, which on Windows is `cmd.exe`, not
bash — a single-quoted glob like `'*.log'` is bash syntax and won't
survive that. Use double quotes: `-g "*.log"`.

## What's required

1. In `src/benchmark.sh`, run `hyperfine` comparing **exactly two**
   commands that both count the same thing — the number of `.log` files
   under `data/filetree/` — by two different means: one using `fd`
   (extension filter), one using `rg` (`--files` with a glob). Use
   `--warmup` (a handful of untimed runs before the timed ones) and
   `--export-json 04-hyperfine-benchmark/results.json` (path relative to
   the module root — the validator reads exactly that file).
2. Run your script, look at the exported JSON (or hyperfine's own
   terminal summary), and fill in `ANSWER.md`:
   - `Winner:` — literally `A` or `B`, matching whichever of your two
     commands you listed first (`A`) or second (`B`) on the `hyperfine`
     command line.
   - `Relative:` — how much faster, as a ratio or percentage (e.g.
     `1.4x faster` or `29% faster`) — read this off hyperfine's own
     summary line, don't compute it from absolute milliseconds by hand.
   - `Why:` — a short honest note on what you think explains the gap (or
     whether it's within noise — that's a legitimate answer too, as long
     as `Winner` still names whichever one the JSON says had the lower
     mean).

The validator **never** asserts an absolute timing threshold. It re-runs
your `src/benchmark.sh`, reads the JSON it exports, and checks that your
stated `Winner` in `ANSWER.md` matches whichever command actually had the
lower `mean` in that JSON.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python generate.py   # once, if data/ doesn't exist yet
uv run python 04-hyperfine-benchmark/tests/validate.py
```

Checks, in order: your script runs and produces
`04-hyperfine-benchmark/results.json`; that JSON has exactly two
commands, each with a recorded warmup count `> 0` and a non-empty
`times` array; `ANSWER.md`'s `Winner` line names `A` or `B` and matches
whichever command's `mean` is actually lower in the JSON; `Relative`
and `Why` are filled in (not placeholders). Prints `PASSED` or
`NOT PASSED: <reason>`.

## Estimated evenings

1

## Topics to read up on

- Why warmup runs matter (page/dentry cache effects on repeated file-tree
  walks)
- Relative vs absolute benchmarking, and why "N ms on my machine" doesn't
  transfer
- What `hyperfine`'s mean/stddev/min/max actually tell you, and when a
  difference is noise vs signal
- `hyperfine --export-json` schema (per-command `times`, `mean`, and
  warmup count)
- Process-startup overhead as a benchmarking confound for very fast
  commands

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
