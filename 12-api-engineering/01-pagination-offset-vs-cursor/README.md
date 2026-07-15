# 01 -- Pagination: offset vs. cursor

## Backstory

Your marketplace API exposes the product catalog one page at a time. The
first version any team ships is the obvious one:

```sql
SELECT id, title, price FROM shop.products
ORDER BY id
LIMIT :limit OFFSET :offset;
```

On page 1 (`offset=0`) it is instant. On page 2, page 3, page 50 -- still
fine. Then a crawler, an "export everything" button, or a bored user holding
the *next* key walks the catalog to page 2,000 (`offset=199900`), and the
same endpoint that felt instant now takes an order of magnitude longer for
the *same* 100 rows. Nothing about the page got bigger. What changed is that
Postgres has no way to jump to the 199,900th row: to satisfy `OFFSET 199900`
it must walk the index in order and produce-then-throw-away every row before
the ones you asked for. Offset pagination does linearly more work the deeper
you page -- the cost is in the rows you *don't* return.

The fix is **keyset** (a.k.a. **seek-method** or **cursor**) pagination:
instead of "skip the first N rows," you say "give me the rows *after* the
last id I saw." Because the ordering column is indexed, the database seeks
straight to that point and reads exactly one page's worth of rows -- page
2,000 costs the same as page 1. This task has you build both endpoints and
then *prove*, with a benchmark on your own machine, why one collapses at
depth and the other stays flat.

## What's given

- `src/app.py` -- a real FastAPI `app` with the two routes defined but their
  bodies `raise NotImplementedError`. The app imports and launches fine; every
  route just answers HTTP 501 until you implement it. The docstrings spell out
  the exact request params, response shapes, and the SQL shape for each.
- The shared, read-only `shop.products` corpus: 200,000 rows, `id` a
  contiguous `1..200000` range, indexed. **Never write to `shop`.**
- The module harness (`harness/common.py`) with ready-made Postgres helpers
  (`pg_pool`, `pg_conn`, `pg_dsn`) and the launch/benchmark plumbing the
  scripts below use.
- `baseline.py` -- the benchmark you run AFTER implementing, to record this
  machine's offset-vs-cursor timings.
- `tests/validate.py` -- the correctness + relative-timing check.

## What's required

Implement both endpoints in `src/app.py`:

- `GET /products/offset?limit=&offset=` -- `LIMIT/OFFSET` over
  `shop.products` ordered by `id`. Returns
  `{"items": [...], "limit": ..., "offset": ...}`; each item at least
  `{"id", "title", "price"}`.
- `GET /products/cursor?limit=&cursor=` -- keyset pagination over
  `shop.products` ordered by `id` ASC, using
  `WHERE id > :cursor ORDER BY id LIMIT :limit` (NOT an offset). Returns
  `{"items": [...], "next_cursor": <id or null when exhausted>}`. `cursor`
  is the last id seen; omit it for the first page.

Both should clamp/guard bad params (negative or huge limit, garbage
cursor/offset) rather than error out -- secondary, but don't skip it.

## Completion criteria

Two steps, run from this task's directory:

```bash
# 1. after implementing src/app.py, record this machine's timings:
uv run python baseline.py

# 2. check correctness + the relative offset-vs-cursor timing:
uv run python tests/validate.py
```

`baseline.py` launches YOUR app and writes shallow-vs-deep timings for both
strategies to a gitignored `pagination-local.json`. `tests/validate.py` then:

- pages your `/products/cursor` from the start to exhaustion and asserts it
  returned every product exactly once (count == 200,000 **and** the id
  checksum matches -- both together);
- checks several `/products/offset` pages against an oracle the validator
  computes itself straight from `shop.products` (it never trusts your app's
  output as truth);
- checks a deep cursor page against that same independent oracle;
- reads `pagination-local.json` and asserts deep-offset latency is
  materially worse than shallow-offset, while cursor latency stays flat with
  depth -- a **relative** check against your own machine's baseline, never an
  absolute millisecond number. (If the baseline file is missing it tells you
  to run `baseline.py` first.)

It prints `PASSED` with the observed counts and the offset-vs-cursor ratio,
or `NOT PASSED: <reason>` and exits 1.

## Estimated evenings

1

## Topics to read up on

- Keyset / seek-method pagination
- `LIMIT`/`OFFSET` cost at depth (why the skipped rows are the expensive part)
- Stable sort keys and tiebreakers for pagination
- Opaque cursor tokens (what to put in a cursor, and why not an offset)

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the `shop` schema, the committed ground-truth values, and the verification
philosophy behind every task in this module -- spoilers. Don't read it before
finishing this task.
