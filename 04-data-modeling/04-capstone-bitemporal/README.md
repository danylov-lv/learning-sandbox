# 04 — Capstone: Bitemporal Modeling

## Backstory

PriceWatch just signed its first enterprise client, and their data team
audits everything. Their first email: "your March 2025 numbers changed
after you published them — which one is correct?" You dig in and confirm
it: roughly 3% of observations arrive more than 24 hours after they
happened (`event_time` vs. `ingested_at` — network retries, shop-side
batching, whatever the cause). Every time you rerun a report, late rows
that weren't there before shift the averages.

The client isn't asking you to eliminate lateness — that's not realistic.
They're asking for two things: tell us how late, and let us reproduce
exactly what we published on any given day, lag and all. This capstone
builds that capability on top of the OLTP tables, SCD2 history, and star
schema from tasks 01–03, then asks you to defend the resulting design in
writing.

The capstone has three checkpoints. Do them in order — CP2 depends on CP1
being real (not faked), and CP3 asks you to explain decisions you can only
explain once you've made them.

## What's given

- Everything from tasks 01–03, live in the same Postgres database.
- `data/clients.jsonl` — 18 clients, each tracking one or more products
  from a given `tracked_since` timestamp (fields: `client_code`,
  `client_name`, `product_code`, `tracked_since`).
- `src/q12.sql`, `src/q13a.sql`, `src/q13b.sql`, `src/q14.sql`,
  `src/q15.sql` — stubs.
- `DESIGN.md` — a template for the CP3 writeup.
- `harness/questions.md` — the exact column/row contract for every
  question (read-only reference; do not edit).

## Checkpoint 1 — Late data (about 1 evening)

The premise starts here: does your schema even know when a row arrived,
separately from when it happened? If your task-01 loader dropped
`ingested_at` on the floor, this checkpoint is where that comes back to
bite you — go fix the base schema/loader before you can answer q13b.

- **q13a**: for each month of 2025, the share of observations whose
  `ingested_at - event_time > 24h` (rounded to 4 decimals).
- **q13b**: for March 2025, average USD price by category as-of, computed
  two ways over the same underlying rows — once using all data, once
  restricted to rows with `ingested_at <= 2025-04-01T00:00:00Z`. At least
  one category is guaranteed to differ between the two columns; if every
  category comes out identical, something in your cutoff filter is wrong
  (a common mistake: filtering on `event_time` instead of `ingested_at`).

Completion: `uv run python harness/validate.py --q q13a,q13b` both print
`PASSED`.

## Checkpoint 2 — Full battery (about 1 evening)

Round out the rest of the capstone-specific questions, then make sure
*everything* in the module still passes together — this is where
duplicate rows, stale as-of joins, or a CP1 fix that broke an earlier
answer would surface.

- **q12**: listings delisted at some point during 2025 and never relisted
  again (as of the end of the stream) -> `(shop_code, product_code,
  delisted_date)`.
- **q14**: per client, how many products they track and how many
  qualifying price-drop events happened on those products since each
  product's `tracked_since` -> `(client_code, tracked_products,
  price_drop_count)`. A price drop is a deduplicated observation priced at
  <=80% of the immediately preceding deduplicated observation on the same
  listing.
- **q15**: monthly observation counts by category as-of, for 2025 ->
  `(month, category, observation_count)`.

Completion:

```
uv run python harness/validate.py --all
```

All 16 questions in the battery (q01–q15, with q13 split into q13a/q13b)
must print `PASSED` in one run.

## Checkpoint 3 — Design review (about 1 evening)

Fill in `DESIGN.md` at the module root of this task. It is not a report
about what you ran — it's a defense of the decisions behind it: where you
denormalized and why, what you'd do differently at 100x scale, how
`event_time` and `ingested_at` actually get you to "reproduce a report
published on day D."

Completion: `DESIGN.md` no longer looks like the empty template (checked
by length, not content — but a two-line answer per section will not clear
the bar, and won't teach you anything either).

## Completion criteria

- CP1: `uv run python harness/validate.py --q q13a,q13b` green.
- CP2: `uv run python harness/validate.py --all` green (all 16 questions).
- CP3: `DESIGN.md` filled in with real substance under every heading.

`uv run python 04-capstone-bitemporal/tests/check.py` runs the DESIGN.md
length check followed by the full battery, and is the single command that
confirms the whole capstone is done.

## Estimated evenings

2-3 (roughly 1 per checkpoint)

## Topics to read up on

- Bitemporal modeling: valid time vs. transaction/system time
- "As of" vs. "as published" queries and why they're different questions
- Ingest lag / late-arriving data patterns in event-sourced pipelines
- Window functions for previous-row comparisons (`LAG` over a partition)
- Table partitioning strategies for append-heavy fact tables at scale
