# 01 — jq: Nested JSON Transformations

## Backstory

A batch of scraper output landed on disk: one big `catalog.json` with pages
of listings nested three levels deep, and a separate `sources.json`
describing where each page came from. Nobody wants to open Python for a
one-off reshape. This is exactly what `jq` is for — but only if you can go
beyond `jq '.foo'` filtering into actual transformation: flattening nested
arrays, joining two documents by key, grouping and aggregating, and
building a new object shape from the result.

## What's given

- `data/scraped/catalog.json` — `{"scraped_at": ..., "pages": [...]}`.
  Each page has a `page_num`, a `source_id`, and a `listings` array. Each
  listing has `listing_id`, `product_id`, `title`, `category`,
  `price_cents` (integer), `currency` (always `"USD"` in this fixture).
- `data/scraped/sources.json` — a flat array of
  `{"source_id", "source_name", "tier"}`, `tier` is one of `"gold"`,
  `"silver"`, `"bronze"`.
- `src/solve.sh` — a stub that currently just exits 1. Fill it in with a
  `jq` invocation (or a short pipeline of them) that reads both files and
  prints the required JSON to stdout.
- `tests/validate.py` — the validator.
- `hints/` — three tiers of hints.

Run `uv run python generate.py` from the module root first if `data/`
doesn't exist yet.

## What's required

Make `src/solve.sh` print, to stdout, a single JSON array. Every listing
across every page counts once. For each **category** that appears in the
catalog, emit one object:

```json
{
  "category": "electronics",
  "listing_count": 42,
  "avg_price_usd": 87.353809523809,
  "tier_counts": {"gold": 20, "silver": 15, "bronze": 7}
}
```

Field definitions, exact:

- `category` — the listing's `category` string.
- `listing_count` — how many listings (across all pages) have this
  category.
- `avg_price_usd` — the mean of `price_cents / 100` over exactly those
  listings. Full precision — do **not** round it yourself; the validator
  compares with a numeric tolerance.
- `tier_counts` — how many of this category's listings came from a page
  whose `source_id` maps (via `sources.json`) to each tier. **All three
  keys** (`gold`, `silver`, `bronze`) must be present, even if a count is
  zero. A page's tier applies to every listing on that page (the join key
  is `source_id`, not per-listing).

The array's element order does not matter — the validator compares by
`category`, not by position. Every category present in the data must have
exactly one object; don't emit duplicates or omit any.

## Completion criteria

Run, from the module root:

```bash
cd toolkit/t3-cli-data-toolkit
uv run python generate.py   # once, if data/ doesn't exist yet
uv run python 01-jq-nested-json/tests/validate.py
```

The validator runs `src/solve.sh`, parses its stdout as JSON, and compares
it against an independent recomputation from the same two source files —
it never trusts your script's output as its own oracle. Prints `PASSED` or
`NOT PASSED: <reason>`.

## Estimated evenings

1

## Topics to read up on

- `jq` object construction (`{key: value}`) vs filtering
- `jq`'s `group_by` and why it requires sorted input first
- `jq`'s `reduce` / `add` for aggregation
- Joining two JSON documents by key in `jq` (building a lookup object,
  `INDEX`)
- `jq`'s `map`, `flatten` / nested `[...]` collection, and `..` recursive
  descent

## Off-limits

`.authoring/` (at the module root) documents this module's grading
contract, not a solution — there are no reference solutions anywhere in
this repository. Read it after finishing this task, if at all.
