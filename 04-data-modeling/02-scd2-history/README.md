# 02 — SCD2 History

## Backstory

The relational core from task 01 answers "what's true now" fine, but the
analysts keep asking "what was true THEN" — what tier was this shop in back
in December, what did we call this product before it got rebranded, what was
this shop's name before its first rename. Your task-01 schema, like most
OLTP schemas, almost certainly keeps only current state: a `shops.tier`
column that gets overwritten in place. That's exactly the kind of query it
can't answer, and it's the same shape of problem that turns into a real
incident report the day someone asks "why did last month's average price by
tier look wrong" and the honest answer is "because we grouped by today's
tier, not December's."

You're adding history tracking for the two attributes analysts keep asking
about: shop name and tier, product brand and category. Backfill it from the
event stream you already have, and answer four as-of questions correctly.

## What's given

- Your loaded schema and database from task 01 (this task builds on top of
  it — don't lose your task-01 tables).
- `src/migration.sql` — header-comment stub: your history DDL and backfill
  logic goes here.
- `src/q05.sql` .. `src/q08.sql` — stubs, one per question below.
- The same event stream and generator guarantees as task 01. The relevant
  admin event types here: `shop_renamed`, `shop_tier_changed`,
  `product_attrs_changed` (payload: `{product_code, changes: {field: value}}`,
  where `field` is `brand`, `category`, or `canonical_title`).

## Semantics

- **As-of state at time t** for an entity = fold all admin events for that
  entity with `event_time <= t`, applied in `event_time` order.
- A shop's initial state comes from its `shop_registered` event;
  `shop_renamed` / `shop_tier_changed` patch `name` / `tier` from their
  `event_time` onward.
- A product's initial attributes (`canonical_title`, `brand`, `category`)
  come from the **first** `product_discovered` event ever recorded for that
  `product_code` — i.e. the earliest `event_time` across all shops that
  discover it. `product_attrs_changed` patches the named field from its
  `event_time` onward. Attributes carried on *later* `product_discovered`
  events (other shops discovering the same already-known product) are
  listing snapshots at discovery time, not attribute changes — ignore them
  for history purposes.

## What's required

1. Design and write history tables in `src/migration.sql` — SCD Type 2
   (validity-interval rows) or an equivalent interval-table design, for:
   - shop `name` and `tier`
   - product `brand` and `category`
   Backfill them from the event stream (reuse whatever staging approach you
   built in task 01, or read `events.jsonl` again directly — your call).
2. Answer four questions in `src/q05.sql`..`src/q08.sql`:
   - **q05** — average USD price by shop tier, where "tier" means the
     shop's tier **as of each observation's own `event_time`**, restricted
     to observations from December 2024. Columns: `(tier, avg_price_usd)`.
     Warning: grouping by the shop's *current* tier instead gives a
     different, wrong answer — the validator's reference numbers were
     checked to actually differ between the two approaches, so this isn't a
     theoretical trap.
   - **q06** — brand of products `P00008`, `P00595`, `P00652` as of
     `2024-04-01T00:00:00Z` and as of `2024-07-01T00:00:00Z`. Columns:
     `(product_code, brand_as_of_d1, brand_as_of_d2)`.
   - **q07** — for shops whose *first* rename happened before
     `2024-09-01T00:00:00Z`: their name as of that cutoff, and their current
     (latest) name. Columns: `(shop_code, name_as_of_cutoff, current_name)`.
     Shops never renamed, or renamed only after the cutoff, are excluded.
   - **q08** — listings whose `product_discovered` event happened while the
     shop's as-of tier was `gold`, counted per shop, plus one `TOTAL` row.
     Columns: `(shop_code, gold_discovered_listings)`.

## Completion criteria

```
uv run python 02-scd2-history/tests/check.py
```

or directly:

```
uv run python harness/validate.py --task 02
```

All four questions must print `PASSED`.

## Estimated evenings

1-2

## Topics to read up on

- Slowly Changing Dimensions Type 2 (validity intervals vs. update-in-place)
- Half-open intervals (`[valid_from, valid_to)`) and why they compose better
  than closed intervals
- Window functions for building intervals from a change log (`LEAD`/`LAG`)
- Range types and exclusion constraints in Postgres (`btree_gist`)
