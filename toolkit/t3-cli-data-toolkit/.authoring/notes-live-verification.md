# Live verification notes (module t3)

Spoilers. Read after finishing the module, not before.

## Tool versions used

- `jq-1.8.1`
- `ripgrep 15.2.0`
- `fd 10.4.2`
- `duckdb` CLI `v1.5.5`
- `hyperfine 1.20.0`
- GNU `parallel 20260722`
- `uv 0.10.9`, Python 3.12 (host) / 3.14 (module `.venv`, via `uv sync`)

## What was verified

All five validators were run from the module root
(`toolkit/t3-cli-data-toolkit`) against the committed stock stubs, then
against a throwaway correct script/invocation, then reverted so only the
stub remains committed. No solving command line is committed anywhere —
every reference invocation used to prove the pass path lived only in
`/tmp` during the session and was copied in, tested, then overwritten
back to the stub byte-for-byte from a `/tmp` backup of the original stub.

| Task | Stock stub | Reference | Reverted |
|---|---|---|---|
| 01-jq-nested-json | `NOT PASSED: src/solve.sh exited 1: not implemented` | `PASSED: 6 categories verified` | yes |
| 02-ripgrep-and-fd | `NOT PASSED: src/solve.sh exited 1: not implemented` | `PASSED: all four answers verified` | yes |
| 03-duckdb-cli-swiss-knife | `NOT PASSED: src/solve.sh exited 1: not implemented` | `PASSED: 6 categories, 5 regions, 120 products verified` | yes |
| 04-hyperfine-benchmark | `NOT PASSED: src/benchmark.sh does not appear to pass --warmup <N> to hyperfine` | `PASSED: Winner B confirmed against results.json (...)` | yes |
| 05-gnu-parallel-batch | `NOT PASSED: src/solve.sh must pass --jobs N (or -j N) with N >= 2` | `PASSED: 30 output files verified against 30 joblog rows` | yes |

Every stock-stub failure is a single `NOT PASSED: <reason>` line with
exit code 1, no traceback — confirmed by inspecting the raw process
output, not just the exit code.

Task 04 additionally had its winner-mismatch branch exercised
deliberately: with a correct `results.json` but `ANSWER.md`'s `Winner:`
flipped to the wrong letter, the validator correctly reported
`NOT PASSED: ANSWER.md says Winner: A, but results.json shows ... the
actually faster one is B` — proving the JSON-vs-ANSWER.md agreement check
is load-bearing, not a no-op.

## `generate.py` determinism

Two consecutive runs of `uv run python generate.py`, hashed as
`find data -type f | sort | xargs sha256sum | sha256sum`, produced the
identical digest:

```
bb74178c60786995c4224663a9a60bee4f0c0ef032b66497b35e1fcca5b20e9a
```

`data/` is 301 KB across 102 files at `SCALE=1.0` — well within the "a
few MB" budget.

## Bugs found and fixed while building this module's own harness

1. **`bash` resolution on native Windows Python.** `subprocess.run(["bash",
   path])` from `uv run python` (a native Windows interpreter) does not
   reliably reach Git Bash — Windows' `CreateProcess` search order checks
   `System32` (a WSL launcher stub also named `bash.exe`) before walking
   `PATH`, so the stub can intercept the call and fail on any
   `D:/...`-style path with a bare "No such file or directory" that reads
   identically to "the script is missing." Fixed by resolving
   `shutil.which("bash")` explicitly in `harness.common._bash_executable`
   (which does walk `PATH` in `PATH` order and finds Git Bash correctly)
   instead of passing the literal string `"bash"` to `subprocess.run` and
   trusting its own lookup.
2. **Backslash-mangled script paths.** Passing a raw `Path` (Windows
   backslashes) as the script argument to Git Bash gets its backslashes
   silently eaten by bash's own argument handling, concatenating
   directory names together. Fixed with `Path.as_posix()` on the script
   path specifically (data-file paths inside the learner's own scripts
   are the learner's problem/lesson, not the harness's).
3. **`duckdb` CLI needs Windows-style paths, not POSIX ones.** Verified
   live while building task 03's throwaway reference: constructing a path
   with `` `pwd` `` inside a Git Bash script gives `/d/Programming/...`,
   which the native `duckdb.exe` cannot open (`IO Error: No files found
   that match the pattern "/d/..."`). `` `pwd -W` `` gives the
   `D:/Programming/...` form DuckDB accepts. Documented in task 03's
   README as a called-out Windows note, not left as a silent trap.
4. **`hyperfine` + single-quoted globs on Windows.** Verified live while
   building task 04's throwaway reference:
   `hyperfine "rg --files -g '*.log' data/filetree"` fails inside
   hyperfine specifically (exit 1 on `rg`'s side) because hyperfine
   shells out through `cmd.exe` by default on Windows, which does not
   strip single quotes the way bash does — `rg` receives the literal
   quoted string as its glob and matches nothing. Double-quoting the glob
   fixed it. Documented in task 04's README and hints.

## Conventions worth keeping if this module is extended

- `harness.common.parse_marker_sections` (the `===Qn===` splitter) is
  reused by tasks 02 and 03 and is generic enough for any future task
  that needs a learner script to emit several labeled answer blocks in
  one stdout stream.
- Every task's "what's required" section pins field names, key sets, and
  rounding/precision rules exactly (unrounded floats + `rel_tol`
  comparison throughout, rather than asking the learner to round and
  guessing at their rounding mode) — this avoids the class of
  false-negative validator bugs that cost time in module 17's
  `check_answers` (see that module's own live-verification notes).
- Task 03's Q3 tie-break rule (earliest `ts` wins) exists specifically
  because the generated data has a real tie at the shipped `SCALE=1.0` —
  don't remove that rule from the README if `generate.py`'s seed or
  scale ever changes; re-check for ties again if it does, since a
  different seed could produce zero ties (rule becomes moot but
  harmless) or more than one (rule stays necessary).
- Task 04's grading is deliberately non-hardcodable: the "ground truth"
  for the Winner check is the learner's own fresh hyperfine run,
  re-executed by the validator itself every time, not a stored value —
  there is nothing to fake short of actually writing a correct
  two-command, warmed-up benchmark and reporting its own outcome
  honestly.
