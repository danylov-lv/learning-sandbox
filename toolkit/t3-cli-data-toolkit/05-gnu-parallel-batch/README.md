# 05 — GNU parallel: Batch Processing

## Backstory

Thirty scraped "pages" landed as separate JSON files — the kind of thing
a producer/consumer spider pipeline drops one file per unit of work.
Summarizing each one is trivial; summarizing thirty of them one at a time
in a `for` loop is a needless sequential bottleneck when they're
completely independent. This is what `parallel` is for: fan the same
per-file command out across all inputs, bounded by an explicit job count,
with a log proving what ran.

## What's given

- `data/batch/inputs/page-NNNN.json` — 30 files, each
  `{"page_id", "source_id", "listings": [{"listing_id", "category",
  "price_cents"}, ...]}`.
- `src/solve.sh` — a stub that currently just exits 1. Fill it in with a
  `parallel` invocation that processes every input file into a
  per-file output.
- `tests/validate.py` — the validator.
- `hints/` — three tiers of hints.

Run `uv run python generate.py` from the module root first if `data/`
doesn't exist yet.

**Note**: `parallel` prints a one-time "Finding the maximal command line
length" notice to stderr (and may prompt about citing) the first time it
runs on a machine. Pass `--will-cite` to suppress the citation notice; it
doesn't affect stdout or the joblog either way, but it's the tidy thing to
do.

## What's required

`src/solve.sh`, run from the module root, must:

1. Use `parallel` with `--jobs <N>` (`N >= 2`) to process every file
   matching `data/batch/inputs/*.json`, writing one output file per input
   into `data/batch/outputs/`, using the **same filename** as the input
   (e.g. `data/batch/inputs/page-0007.json` →
   `data/batch/outputs/page-0007.json`).
2. Pass `--joblog data/batch/joblog.txt` so there's a record of every job
   `parallel` ran (path relative to the module root — the validator reads
   exactly that file).

Each output file must be a JSON object with this exact shape:

```json
{
  "page_id": "page-0007",
  "listing_count": 5,
  "total_price_usd": 412.37,
  "avg_price_usd": 82.474,
  "categories": ["electronics", "home"]
}
```

Field definitions, exact:

- `page_id` — copied from the input file's `page_id`.
- `listing_count` — number of entries in the input's `listings` array.
- `total_price_usd` — sum of `price_cents / 100` over all of that page's
  listings. Full precision — do not round it yourself.
- `avg_price_usd` — `total_price_usd / listing_count`. Full precision.
- `categories` — the **distinct** `category` values among that page's
  listings, sorted ascending. No duplicates.

How you produce each output (a `jq` filter, a small script, anything) is
your call — `parallel`'s job is fanning that per-file command out across
all 30 inputs, not doing the transformation itself.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python generate.py   # once, if data/ doesn't exist yet
uv run python 05-gnu-parallel-batch/tests/validate.py
```

The validator wipes `data/batch/outputs/` and `data/batch/joblog.txt`,
runs `src/solve.sh`, then checks: `--jobs N` (`N >= 2`) and `--joblog` are
actually present in your script; `data/batch/joblog.txt` has exactly one
row per input file, every one exit code `0`; and — the real check — every
expected output file exists with content matching a reference this
validator computes independently in Python from the same input files, not
from your script's own output. Prints `PASSED` or `NOT PASSED: <reason>`.

## Estimated evenings

1

## Topics to read up on

- `parallel`'s `:::` input-source syntax vs piping filenames on stdin
- `{}`, `{/}`, `{.}`, `{/.}` replacement strings and when each one matters
- `--jobs` (how many workers) vs `--joblog` (what a job log actually
  records — exit codes, timing, the exact command run)
- Why `parallel` warns about "citing" on first use, and `--will-cite`
- What makes a per-file transform safe to parallelize at all (no shared
  mutable state, no ordering dependency between files)

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
