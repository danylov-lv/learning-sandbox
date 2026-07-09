# 06 — Delta Lake

## Backstory

PriceWatch's scrapers do not stop. Every scrape run drops another batch of
JSONL, and someone (a cron job, a human backfilling a gap, an analyst
re-running a source) is going to append to the lake continuously from now
on. Tasks 01-05 gave you a very good plain-Parquet lake, but plain Parquet
directories have three problems that only show up once you stop treating
the lake as a one-time build:

- **No atomicity.** Last month, a scrape-ingestion job died halfway through
  writing a batch of Parquet files. Half the files for that run existed,
  half did not. The next query against that partition double-counted rows
  from the files that landed before the crash and undercounted the ones
  that never got written — nobody noticed until finance asked why November
  GMV moved between two runs of the same query.
- **No schema evolution story.** The moment you want to add a derived
  column to an existing dataset, you are choosing between rewriting
  everything or living with two subtly different schemas in the same
  directory that downstream readers have to special-case.
- **No history.** "What did this table look like yesterday, before the bad
  batch landed" is not answerable from a directory of Parquet files. You
  would need a separate backup process, taken on faith to have run.

A **table format** sits on top of Parquet and fixes all three by adding a
transaction log: every write is a numbered, atomic commit recorded as JSON
actions (add these files, remove those files, change this schema). Readers
never see a partial commit — they either see the table as of commit N or
commit N+1, never something in between. Because every commit is numbered,
"the table as of yesterday" becomes "the table as of version N," and you
can go back to it just by asking.

You are going to rebuild the PriceWatch snapshot lake as a
[Delta Lake](https://delta.io) table using `delta-rs` (the `deltalake`
Python package — no Spark, no JVM), and put every one of those three
failure modes through its paces: an atomic multi-commit append, a
schema-evolving column addition, and a time-travel query against a version
that predates that column.

## What's given

- `data/raw/part-*.jsonl` and `data/ground-truth.json` from the module
  generator (see the module README to (re)generate).
- MinIO running (`docker compose up -d --wait` from the module root),
  bucket `price-lake` already created, credentials in
  `harness/common.py`.
- `src/delta_pipeline.py` — a scaffold with the full contract for each
  function in its docstring. You implement all of it.
- `tests/validate.py` — the validator.

## What's required

Implement four functions in `src/delta_pipeline.py`:

1. **`initial_load(raw_dir, table_uri) -> int`** — stream
   `data/raw/*.jsonl` and write a Delta table at `table_uri`, partitioned
   by a derived `month` string column (`"YYYY-MM"`, from `captured_at` in
   UTC), zstd-compressed, using the same 13-column contract as the earlier
   tasks (see the scaffold docstring for the exact column list and types)
   plus the extra `month` partition column. Write **every month except the
   chronologically last one** — that month is held back for step 2. This
   has to be a single atomic commit even though you stream the input in
   bounded-size chunks; delta-rs can consume a streaming Arrow source
   directly, so "stream in, one commit out" is achievable without
   buffering the whole dataset. Return the row count written.

2. **`append_last_month(raw_dir, table_uri) -> int`** — append the
   month you held back, but not as one write. Split it into several
   fixed-size row batches and call the append write once per batch, so the
   held-back month lands as **multiple separate commits**, `mode="append"`
   each time. This is deliberately the "many small commits" anti-pattern —
   it is exactly what a scraper that flushes a batch every N rows produces
   in production, and it is what sets up the small-files problem you fix
   in step 4. Return the total row count appended.

3. **`add_price_bucket(table_uri) -> None`** — schema evolution without
   a rewrite: add a nullable `price_bucket` string column to the table's
   schema. Every file written before this point stays exactly as it is on
   disk; only the schema in the transaction log changes. Older versions of
   the table must still report the old (pre-`price_bucket`) schema when
   you time-travel to them.

4. **`compact(table_uri) -> dict`** — clean up the small-files mess from
   step 2: compact the table's files, then vacuum the ones compaction made
   obsolete so they are actually deleted, not just orphaned. Return
   whatever metrics dict the compaction call gives you back. **Vacuuming
   with a short retention window is a foot-gun in production** — the
   default retention exists so that a reader who opened the table before
   your compaction (and is still mid-scan against the old files) does not
   have the ground pulled out from under it, and so that time travel to
   recent versions keeps working. You are going to override that default
   for this task; say in your `NOTES.md` why you would not do that against
   a table anyone else might be reading concurrently.

Then, in `if __name__ == "__main__":`, run steps 1-4 in order against a
local table at `data/delta/snapshots`. `data/delta/` is gitignored — it is
your scratch output, not tracked.

### And once more, on MinIO

Everything above works identically against an S3-compatible object store —
that is the entire point of a table format built on object storage rather
than a filesystem, not a filesystem-specific trick. After the local run,
repeat steps 1-2 only (no schema evolution, no compaction) against
`s3://price-lake/delta/snapshots`, passing `storage_options` to
`write_deltalake`/`DeltaTable`. You will need to figure out which
`storage_options` keys make delta-rs talk to MinIO instead of real AWS —
wrong-endpoint or wrong-scheme failures here are informative, not just
annoying; read them. `harness/common.py` has the MinIO endpoint and
credentials to build the options dict from.

Run:

```bash
uv run python 06-delta-lake/src/delta_pipeline.py
uv run python 06-delta-lake/tests/validate.py
```

Fill in `NOTES.md`: how many versions did the finished table have, and
what operation was each one? How many files existed in the last month's
partition right before compaction, and right after? What broke (if
anything) the first time you tried the vacuum call, and why does the
default retention window exist? If you attempted the MinIO stretch, what
`storage_options` did you end up needing, and what error told you which
one was missing?

## Completion criteria

`tests/validate.py` prints `PASSED`. It checks, all against the local
table at `data/delta/snapshots`:

- the latest version's row count equals `ground-truth.json`'s
  `total_rows`, and per-month price sums match `price_sum_by_month`
  (relative tolerance 1e-6);
- time travel: at the version immediately before the first `append`-mode
  commit, the row count equals `total_rows` minus the last month's row
  count, and that month's partition is absent entirely at that version;
- the table's history contains at least two `append`-mode commits after
  the initial write (the multi-commit append from step 2);
- the latest schema contains `price_bucket`; the schema at version 0 does
  not;
- the history contains an `OPTIMIZE` operation whose metrics show more
  files removed than added, by a wide margin, and the last month's
  partition ends up with only a handful of physical files after
  compaction — while the row count is unchanged from before compaction;
- the MinIO table at `s3://price-lake/delta/snapshots` loads, has at least
  one commit past its initial write, and its row count equals
  `total_rows` (the local table's initial load + appends have no
  MinIO-side compaction step, so its file count will look different from
  the local table — that is expected);
- `NOTES.md` filled in beyond the template.

## Estimated evenings

2

## Topics to read up on

- The Delta transaction log: numbered commits, JSON actions (add/remove
  file, metadata change), and how a reader reconstructs table state from
  it
- Optimistic concurrency control for table writes, and why it needs the
  storage layer to support an atomic "put if this version number is still
  current" operation
- Time travel: querying a table as of a specific version or timestamp
- Schema evolution vs. schema enforcement, and why adding a nullable
  column never requires touching existing data files
- Compaction (bin-packing small files into fewer larger ones) and vacuum
  (deleting files no longer referenced by any commit within the retention
  window)
- Why object stores historically lacked atomic rename/conditional-write
  primitives, and what a table format needs from the storage layer to get
  ACID semantics on top of one anyway
