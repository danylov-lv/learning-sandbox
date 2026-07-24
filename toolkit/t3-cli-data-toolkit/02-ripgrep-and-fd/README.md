# 02 — ripgrep + fd Fluency Drills

## Backstory

Someone dumped a spider workspace on you: run logs, source files, config
snippets, a `vendor/` directory full of third-party junk you don't own.
Before touching any of it you need four quick facts, and reaching for a
Python script for each one would be slower than just knowing your tools.
This task is four independent drills in one script — regex with a capture
group, `fd` globbing with an exclusion, a lookaround-style pattern, and a
file-count-by-extension census.

## What's given

- `data/filetree/` — a generated directory tree:
  - `logs/day-NN/*.log` — spider run logs, lines like
    `... status=200 price=19.99`.
  - `src/core/`, `src/utils/`, `src/web/` — `.py` and `.js` source files.
  - `docs/*.md` — free-form notes.
  - `config/**/*.config.json` — nested config files.
  - `vendor/pkg/` — third-party junk (`.js` and `.config.json` files) you
    should usually exclude from searches, but that still exists on disk.
- `src/solve.sh` — a stub that currently just exits 1. Fill it in to print
  four labeled answer blocks to stdout (exact format below).
- `tests/validate.py` — the validator.
- `hints/` — three tiers of hints.

Run `uv run python generate.py` from the module root first if `data/`
doesn't exist yet.

## What's required

Make `src/solve.sh` print exactly this shape to stdout — four sections,
each starting with its own `===Qn===` marker line:

```
===Q1===
<answer>
===Q2===
<answer, possibly multiple lines>
===Q3===
<answer>
===Q4===
<answer, multiple lines>
```

**Q1 — regex with a capture group.** Across every `*.log` file under
`data/filetree/logs/` (recursively), find lines matching `status=(5\d\d)` —
an HTTP 5xx status. Collect the **distinct** captured status codes, sort
them ascending, and print them comma-separated with no spaces on one line
(e.g. `500,502,503,504`).

**Q2 — `fd` glob excluding a directory.** List every file under
`data/filetree/` matching the glob `*.config.json`, recursively, but
**excluding anything under a `vendor/` directory**. Print one path per
line, as a path relative to `data/filetree/` using forward slashes (e.g.
`config/env/component-001.config.json`), sorted ascending. `vendor/`
itself does contain matching files — they must not appear in your answer.

**Q3 — a lookaround pattern.** Across every `.py` and `.js` file under
`data/filetree/src/` (recursively — this excludes `vendor/`), count the
total number of **matches** (not lines — a line with two matches counts
twice) of the word `price` where it is **not** immediately followed by
`_usd`. That's a negative lookahead: `price(?!_usd)`. Print just the
integer.

**Q4 — census by extension.** Across the entire `data/filetree/` tree
(recursively, `vendor/` included this time), count files by extension for
exactly these five extensions: `py`, `js`, `log`, `md`, `json`. Print one
`ext:count` line per extension, sorted alphabetically by extension name,
extension without the leading dot (e.g. `js:18`). A file named
`component-001.config.json` counts as `json` (its extension is whatever
follows the last dot).

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python generate.py   # once, if data/ doesn't exist yet
uv run python 02-ripgrep-and-fd/tests/validate.py
```

The validator runs `src/solve.sh`, parses the four `===Qn===` blocks from
its stdout, and compares each against an independent recomputation done
in plain Python (`re` + `pathlib`, not by re-running `rg`/`fd` themselves)
over the same `data/filetree/` tree. Prints `PASSED` or
`NOT PASSED: <reason>`.

## Estimated evenings

1

## Topics to read up on

- Regex capture groups and how to extract only the captured text
  (`rg -o -r '$1'` vs plain `-o`)
- `fd`'s glob mode (`-g`/`--glob`) vs its default regex mode, and `-E`/
  `--exclude`
- Lookahead/lookbehind assertions and why `rg` needs `-P` (PCRE2) to
  support them at all
- Counting matches vs counting matching lines (`rg -c` vs `rg -o | wc -l`)
- `fd -e`/`--extension` and how it differs from a raw glob on the
  filename's suffix

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
