# Authoring notes — 03-data-modeling (PriceWatch)

Spoiler zone. Committed, not gitignored, but off-limits to the learner
before finishing a task (README says so). Written for a future generation
session extending this module without re-deriving the design.

## Why an event stream, not a schema

The learner gets zero schema and one raw business-event log
(`harness/events.py` -> `data/events.jsonl`, ordered by `ingested_at`/arrival,
not `event_time`/business order). This gives every task in the module (OLTP,
SCD2, star schema, bitemporal capstone) exactly one ground truth to model
against, computed independently by `harness/ground_truth.py` straight from
the stream — never from any learner-authored schema. That's what makes
"no reference solutions" tenable: the validator doesn't need a solved
schema to check against, it needs the event stream, which already exists.
Event types: `shop_registered`, `shop_renamed`, `shop_tier_changed`,
`product_discovered`, `product_attrs_changed`, `product_delisted`,
`product_relisted`, `price_observed`.

## Semantics contract (must never drift between events.py / ground_truth.py / questions.md)

- **Business time vs ingest time**: `event_time` = when it happened;
  `ingested_at` = when the system learned about it. Everything is bucketed
  by `event_time` except q13a/q13b, which exist specifically to probe the
  gap.
- **As-of state**: fold all admin events for an entity with
  `event_time <= t`, in `event_time` order. Applies to shop name/tier and
  product brand/category alike.
- **Shop state**: `shop_registered` sets initial name/country/tier;
  `shop_renamed` patches name; `shop_tier_changed` patches tier; country is
  immutable.
- **Product attrs — first-discovery-wins**: canonical_title/brand/category
  come from the *first* `product_discovered` event ever seen for that
  `product_code` (earliest `event_time` across all shops listing it).
  `product_attrs_changed` patches from its own `event_time` onward. Later
  `product_discovered` events (other shops discovering an already-known
  product) are listing snapshots only and must never feed attribute
  history — this is the single easiest thing for a learner (or a future
  generation session) to get wrong when reimplementing as-of logic.
- **Listings**: `(shop_code, product_code)` pair; active from
  `product_discovered`, inactive from `product_delisted`, active again from
  `product_relisted`, arbitrarily many cycles.
- **Dedup rule**: `price_observed` unique by
  `(shop_code, product_code, event_time)`. ~1% exact duplicates collapse to
  the first-arriving copy (smallest `ingested_at`) — since the file is
  itself arrival-ordered, this is "first occurrence encountered when
  streaming the file top to bottom," no sort needed.
- **USD conversion**: static `FX_TO_USD` in `harness/common.py`
  (`USD=1.0, EUR=1.08, GBP=1.27`), rounded to 4 decimals throughout —
  deliberately no historical FX drift, since the point is schema design,
  not currency accuracy.

## Generator guarantees relied on by every task and by ground_truth.py

- `shop_registered` precedes any other event for that shop.
- `product_discovered` for a listing precedes that listing's observations.
- Admin events arrive in `event_time` order relative to each other *per
  entity* (interleaving across entities is fine and expected).
- No two distinct prices share `(shop_code, product_code, event_time)` —
  if the triple repeats, it's the same observation duplicated, not a
  coincidental second observation.

## Question -> task mapping and fixed parameters

Directory names are authoritative: `01-relational-core`,
`02-scd2-history`, `03-star-schema`, `04-capstone-bitemporal` (matches
`harness/validate.py`'s `TASK_QUESTIONS`/`DEFAULT_SQL_PATH`). Empty stub
directories from an earlier 7-task numbering draft (`01-oltp-core`,
`02-price-history`, `03-scd2-dimensions`, `04-hard-questions`,
`05-denormalization-measured`, `06-star-schema`, `07-capstone-migration`)
were removed during generation; only the four names above exist.

- **Task 01 (q01-q04)**: q02 top-10 products (`TOP10_PRODUCTS`):
  `P00001, P01996, P01001, P00004, P00998, P01995, P01000, P01999, P00002,
  P00999`. q04: product `P00001`, window `2025-01-01T00:00:00Z` + 60 days.
- **Task 02 (q05-q08)**: q05 as-of month `2024-12`. q06 products
  `P00008, P00595, P00652` at `d1=2024-04-01T00:00:00Z`,
  `d2=2024-07-01T00:00:00Z`. q07 cutoff `2024-09-01T00:00:00Z`.
- **Task 03 (q09-q11)**: all scoped to calendar year 2025 (q09 monthly, q10
  H1 window, q11 quarterly top-5 brands). No fixed IDs beyond the year.
- **Task 04 (q12-q15)**: q12 year `2025`. q13a/q13b month `2025-03` (q13a is
  the monthly late-share series for all of 2025; q13b's cutoff comparison
  is specifically March 2025 with ingest cutoff `2025-04-01T00:00:00Z`).
  q14 drop rule: price `<= 80%` of the immediately preceding deduplicated
  observation for the same listing (a >=20% single-step drop), counted
  from the client's per-product `tracked_since` onward, summed across all
  listings of that product. q15 is q09's bucketing without the price
  average (count only).

## Non-degeneracy assertions baked into ground_truth.py

These exist so a lazy or subtly-wrong learner schema (or a future
regenerated dataset) can't accidentally produce a battery that's trivially
satisfied by the wrong model. If any of these ever fail after a data
regeneration, the scale/seed/date range changed enough to need a fixed-param
review:

- q03: deduplicated count must differ from raw line count (dedup is
  actually exercised) — current dedup delta is 23010 rows.
- q04: every one of the 60 window days must have at least one observation
  (no silent gap days).
- q05: as-of-tier grouping must differ from final-tier grouping (i.e. at
  least one shop's tier changed before 2024-12 in a way that matters —
  otherwise q05 wouldn't distinguish as-of history from "just join current
  tier").
- q06: at least one of the three fixed products must show a brand change
  between d1 and d2.
- q07/q08/q12: result sets must be non-empty.
- q13b: at least one category's cutoff-restricted average must differ from
  its full-data average (late arrivals actually change March's reported
  numbers under a cutoff).

## Star-schema validator contract (harness/validate.py)

- Schema must be named `mart`; required tables `dim_shop`, `dim_product`,
  `dim_date`, `fact_price_observation`, all non-empty.
- `dim_shop` and `dim_product` must each have `valid_from` and `valid_to`
  columns.
- For q09/q10/q11 the validator runs `SET search_path = mart` before
  executing the learner's SQL and rejects any query text matching
  `\bpublic\s*\.` — the star-schema questions must be answerable from
  `mart` alone, no reaching back into the OLTP/history schema.
- `star_schema_precheck` runs once per invocation whenever any of q09/q10/
  q11 are requested; failure short-circuits those three with a single
  `NOT PASSED` reason rather than three separate connection attempts.

## Verification status (as of this authoring pass)

- `data/` already generated at scale 1.0, seed 42: 2,336,793 events, 50
  shops, 2400 products, 10613 listings, 18 clients. `events.meta.json` sha
  `bdaede4...` (events), clients sha `eef334d...`.
- `ground_truth.json` cache is keyed by those shas (via `events.meta.json`)
  — regenerating the stream with the same seed/scale reuses the cache;
  any drift in generator logic invalidates it automatically.
- `validate.py`'s comparison machinery (column-name/order check, row
  multiset match with float tolerance 1e-3, timestamp/date/decimal
  normalization, star-schema precheck, fail-path messaging) has been
  exercised against a live Postgres instance for both the pass path and
  deliberate fail paths (missing file, stub file, wrong columns, public.
  schema reference on star questions). No task SQL files or reference
  answers are committed anywhere in the repo by design — the full
  `--all` battery cannot go green without the learner actually solving
  every task; that's the intended state at hand-off, not a gap to fix.
