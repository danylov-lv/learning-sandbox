# Module t3 design notes — OFF-LIMITS TO THE LEARNER BEFORE FINISHING A TASK

This directory (`.authoring/`) is committed but must not be read before
you attempt a task — see `CONVENTIONS.md`. There are no reference
solutions here (there never are, anywhere in this repo): this file
documents the grading *contract* and the exact expected answers each
validator recomputes, not a solving command line. Read it after
finishing a task, if at all.

## Shared infrastructure

- `generate.py` (module root) is the single fixture generator for all
  five tasks, seed `SEED = 20250713` (a fixed `numpy.random.default_rng`
  seed, not date-derived), respecting `SCALE` (default `1.0`). Verified
  deterministic: two consecutive runs produce byte-identical `data/`
  trees (`sha256sum` over every file's hash, sorted by path, then
  hashed again — see `notes-live-verification.md` for the recorded
  digest).
- `harness/common.py` was copied from `17-system-design/harness/common.py`
  (same `guarded`/`passed`/`not_passed` semantics) and then extended with
  process/data helpers this module actually needs: `run_script` (invokes
  `bash <script>`, resolving the `bash` executable via `shutil.which`
  rather than trusting subprocess's own PATH search — see the Windows
  gotcha below), `parse_marker_sections` (splits stdout on `===LABEL===`
  lines, used by tasks 02 and 03), `require_data`, `check_close`,
  `check_json_equal`.
- Every validator is an expected-output check: it runs the learner's
  script for real, then diffs the result against a ground truth computed
  independently in this process (stdlib `re`/`pathlib`, `pandas`, or
  `duckdb`-as-a-Python-library over the same fixture files) — never by
  re-invoking the learner's own command with different flags.

### Windows/Git Bash gotcha (load-bearing, cost real debugging time)

`subprocess.run(["bash", path, ...])` from a **native Windows** Python
(what `uv run python` uses here) does not reliably land on Git Bash. On
Windows, `CreateProcess`'s own search order checks `C:\Windows\System32`
(where a WSL launcher stub named `bash.exe` lives) **before** it walks
`PATH`, so a bare `"bash"` argv can silently resolve to the WSL stub
instead of Git Bash. That stub cannot open a `D:/...`-style path at all
and fails with a bare "No such file or directory" that looks identical to
"the script doesn't exist." Fix: resolve `shutil.which("bash")` explicitly
in Python (which walks `PATH` itself, in `PATH` order, and correctly
finds Git Bash) and pass that resolved absolute path to `subprocess.run`
instead of the bare string `"bash"`. This is `harness.common._bash_executable`.
Separately, `Path.as_posix()` (forward slashes) must be used for the
script path argument itself — passing a raw Windows path with backslashes
gets mangled by Git Bash's own argument parsing.

## Task 01 — jq-nested-json: exact ground truth

Source files: `data/scraped/catalog.json` (`pages[].listings[]`, each
listing has `category`, `price_cents`), `data/scraped/sources.json`
(`source_id -> tier`, one of `gold`/`silver`/`bronze`).

For each **category** appearing anywhere in the catalog:

- `listing_count` = count of listings with that category, across all
  pages.
- `avg_price_usd` = `sum(price_cents / 100 for matching listings) /
  listing_count`, unrounded, compared with `rel_tol=1e-6`.
- `tier_counts` = `{gold, silver, bronze}`, all three keys always present
  (zero-filled), counting how many of that category's listings came from
  a page whose `source_id` maps to each tier. The join key is
  `source_id` at the **page** level, not per-listing — every listing on
  a page inherits that page's source's tier.

Validator compares the learner's JSON array to this dict keyed by
`category`; array order is not checked (compared as a dict, not a list).

## Task 02 — ripgrep-and-fd: exact ground truth

All computed over `data/filetree/` using Python `pathlib.rglob` + `re`,
never by invoking `rg`/`fd` inside the validator.

- **Q1**: `re.compile(r"status=(5\d\d)")` applied per-line to every
  `*.log` file under `data/filetree/logs/` (checked via
  `"logs" in path.relative_to(filetree).parts`, so it's specifically the
  `logs/` subtree, not any `.log` file anywhere). Distinct captured
  groups, sorted ascending as strings (safe because they're always
  exactly 3 digits starting with `5`, so string sort == numeric sort),
  joined with commas, no spaces. With the shipped fixture at `SCALE=1.0`
  this is `500,502,503,504` (all four are guaranteed present because the
  generator's status-code weight table always samples enough volume to
  hit p1 in practice at the shipped scale, but the validator never
  hardcodes this list — it recomputes from whatever `data/filetree/`
  actually contains).
- **Q2**: `filetree.rglob("*.config.json")`, filtered to drop any path
  whose parts include `"vendor"`, then `.relative_to(filetree).as_posix()`,
  sorted ascending. Compared as a sorted list (order matters after
  sorting, since both sides sort identically).
- **Q3**: `re.compile(r"price(?!_usd)")`, applied with `.findall()` per
  line (not per file) across every `*.py` and `*.js` file under
  `data/filetree/src/` (`rglob`, so `src/core`, `src/utils`, `src/web`
  all included; `vendor/` is a sibling of `src/`, not under it, so it's
  naturally excluded). Summed as **match count**, not line count — a line
  with two occurrences counts twice.
- **Q4**: for every file under `data/filetree/` (`rglob("*")`, `is_file()`
  only, `vendor/` included), bucket by `path.suffix.lstrip(".")`, counted
  for exactly `{py, js, log, md, json}`. A file named
  `component-001.config.json` buckets as `json` (last-dot suffix), which
  is why Q4's total for `json` differs from Q2's config-file count — Q4
  counts `vendor/`'s config/js files too, Q2 excludes them.

## Task 03 — duckdb-cli-swiss-knife: exact ground truth

Computed with `pandas.read_parquet(parquet_dir)` (which auto-discovers
the `category=<value>` hive partitions as a real column) and
`pandas.read_csv(products.csv)` — not by re-running the learner's SQL,
and not via `duckdb`-as-a-library either (plain pandas was simpler and
avoids depending on DuckDB's own SQL semantics agreeing with itself).

- **Q1**: `obs.groupby("category")["price"].agg(["count", "mean"])`
  across every observation (no product/time filtering).
- **Q2**: `obs.merge(products[["product_id","region"]], on="product_id",
  how="inner").groupby("region")["price"].agg(["count","mean"])`.
- **Q3**: sort by `(product_id, ts)`; `delta = groupby("product_id")
  ["price"].diff()`; drop the first row per product (`NaN` delta); within
  each product, sort by `(delta DESC, ts ASC)` and take the first row —
  this is the tie-break rule stated in the README (earliest `ts` wins a
  tie). **Verified live**: at `SCALE=1.0`, exactly one product
  (`WP00084`) has a genuine tie (`delta == 0.66` at both
  `2026-02-13T12:00:00` and `2026-02-14T15:00:00`) — this is why the
  README states the tie-break rule explicitly instead of leaving it
  ambiguous; without it, a learner's `ROW_NUMBER() OVER (... ORDER BY
  delta DESC)` (no secondary sort key) could legitimately pick either row
  and disagree with an unspecified oracle.
- Float comparisons use `rel_tol=1e-6` (Q1/Q2 `avg_price`) and
  `rel_tol=1e-6, abs_tol=1e-4` (Q3 `jump_amount`, slightly looser because
  it's a difference of two already-rounded-to-cents floats).

## Task 04 — hyperfine-benchmark: grading contract

No independent "correct count" oracle is needed or computed — this task
grades *methodology and self-consistency*, not a data answer:

1. `src/benchmark.sh`'s source text must contain `--warmup\s*\d+` (regex
   `--warmup(?:[= ]|\s+)\d+`) — checked structurally on the script text,
   since hyperfine's exported JSON schema does not itself record whether
   `--warmup` was used (confirmed by inspecting real `--export-json`
   output: it has `command`, `mean`, `stddev`, `median`, `user`,
   `system`, `min`, `max`, `times[]`, `memory_usage_byte[]`,
   `exit_codes[]` — no warmup field at all).
2. The validator deletes any stale `results.json`, runs
   `src/benchmark.sh` for real (`cwd=MODULE_ROOT`, 180s timeout), and
   requires the exported `04-hyperfine-benchmark/results.json` to have
   `results` as a list of **exactly 2** entries (module spec says
   "assert >=2 commands"; this task's `ANSWER.md` A/B scheme only makes
   sense for exactly 2, so `>=2` is checked first with a generic message,
   then `==2` specifically for this task), each with non-empty `times`.
3. `ANSWER.md`'s `Winner:` line must be exactly `A` or `B`, mapped to
   `results[0]`/`results[1]` respectively (hyperfine's JSON preserves
   CLI argument order — confirmed live). The validator computes
   `actual_winner = "A" if results[0]["mean"] < results[1]["mean"] else
   "B"` and requires exact agreement. This is inherently non-hardcodable:
   the "ground truth" is the learner's own fresh measurement, re-run by
   the validator, not a stored value — so there's nothing to fake except
   by actually running a correct two-command benchmark and reading its
   own result honestly.
4. `Relative:` and the `## Why` section just need to be present,
   non-placeholder (no literal `[fill in`), and `## Why` at least 15
   characters — light checks, since the actual grading load-bearing bit
   is the Winner/JSON agreement.

**Windows gotcha verified live**: `hyperfine "rg --files -g '*.log' ..."`
(single-quoted glob) fails with exit 1 inside hyperfine specifically
because hyperfine invokes benchmarked commands through `cmd.exe` on
Windows by default, and `cmd.exe` doesn't strip single quotes — `rg`
receives the literal 7-character argument `'*.log'` (quotes included) as
its glob and matches nothing, so it exits 1 ("no match" is `rg`'s
convention). Confirmed the fix (`-g "*.log"`, double quotes) resolves it.
This is called out explicitly in the task README and hints because it is
exactly the kind of gotcha that silently sends a learner down a "why does
my benchmark keep failing" hole unrelated to hyperfine itself.

Reference commands used to prove the pass path (not committed anywhere):
`fd -e log . data/filetree | wc -l` vs
`rg --files -g "*.log" data/filetree | wc -l` — both count the fixture's
12 `.log` files (at `SCALE=1.0`); which one is faster varied slightly
run-to-run in live testing (noise-dominated at this data size, as
expected for two sub-50ms Rust binaries), which is fine and expected
because the validator only checks self-consistency against the learner's
own fresh JSON, never an absolute or a "correct" winner.

## Task 05 — gnu-parallel-batch: exact ground truth

Computed per input file (`data/batch/inputs/page-NNNN.json`, `listings[]`
each with `category`, `price_cents`) directly in Python:

- `page_id` = input's `page_id`, unchanged.
- `listing_count` = `len(listings)`.
- `total_price_usd` = `sum(l["price_cents"] for l in listings) / 100`,
  unrounded.
- `avg_price_usd` = `total_price_usd / listing_count`, unrounded.
- `categories` = `sorted(set(l["category"] for l in listings))`.

Compared field-by-field against `data/batch/outputs/<same-filename>.json`
for every input file, with `rel_tol=1e-6` on the two float fields.

Structural parallelism checks (script text + joblog), independent of the
content check:

- Script text must contain the literal substring `parallel`, a
  `--jobs`/`-j` flag with an integer `>= 2` (regex
  `(?:--jobs(?:[= ]|\s+)|-j\s*)(\d+)`), and the literal substring
  `--joblog`.
- After running, `data/batch/joblog.txt` must exist with a header row
  containing an `Exitval` column and exactly one job row per input file
  (30 at `SCALE=1.0`), every row's `Exitval` column equal to `"0"`.
- The validator wipes `data/batch/outputs/` and the joblog before every
  run, so a stale directory from a previous debugging session can't
  silently satisfy the "output exists" check without this run's script
  actually having produced it.

**GNU parallel first-run stderr note (from the module spec, verified
live)**: `parallel`'s "Finding the maximal command line length" notice
(and a citation nag) go to stderr on first use on a machine; the
validator never reads `result.stderr` for parsing (only for the tail-line
error message on a non-zero exit), so this is a non-issue as implemented
— it was a deliberate design constraint, not something worked around
after the fact.
