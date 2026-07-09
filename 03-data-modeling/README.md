# Module 03 — Data Modeling

## Backstory

PriceWatch is a price-tracking platform: shops list products, prices get
observed over time, and clients track products for drop alerts. You've been
handed the thing every schema-design exercise pretends doesn't exist: not a
spec, not an ER diagram, but a raw firehose of business events as they
actually happened — `shop_registered`, `product_discovered`,
`price_observed`, `shop_renamed`, `product_attrs_changed`,
`product_delisted`/`relisted`, `shop_tier_changed` — arriving out of business
order, with duplicates, with stragglers that show up weeks late. Your job is
to design the schema, not just query one that already exists.

This is where module 02's optimization instincts meet a different question:
not "how do I make this query fast" but "what should this table even look
like." You'll build the same PriceWatch data up through four increasingly
demanding shapes: a normalized OLTP core, SCD2-style history, a Kimball star
schema, and full bitemporal reasoning over late-arriving data — each one a
different answer to "how do I represent change over time."

## What this trains

- **Normalization vs. denormalization** — where 3NF earns its keep (task 01)
  and where a flattened, pre-joined shape earns its keep instead (measured,
  not assumed, later in the module).
- **SCD Type 2** — representing "what was true when" for slowly-changing
  attributes (shop tier, product brand) without replaying the event log
  every time someone asks an as-of question.
- **Star schema on top of OLTP** — Kimball dimensional modeling
  (conformed dimensions, a fact table, SCD2 dims with `valid_from`/
  `valid_to`) built *from* the OLTP/history layer, not from scratch.
- **Bitemporality and late data** — the gap between *business time*
  (`event_time`, when something happened) and *ingest time* (`ingested_at`,
  when your system learned about it), and what it costs you when the two
  disagree.

This is the SPEC theme for the module: every task is a different lens on
"how do you model change," using one dataset throughout.

## Quick start

```bash
cd 03-data-modeling
docker compose up -d --wait          # Postgres 16 on port 54303
uv sync
uv run python harness/events.py      # writes data/events.jsonl + clients.jsonl (seed 42, deterministic)
```

Postgres is reachable at `localhost:54303`, db/user/password all `sandbox`
(port overridable via `SANDBOX_03_PORT`). Then read `harness/questions.md` —
it is the learner-facing contract for the full q01–q15 battery: what each
answer must contain, column by column, independent of how you choose to
model anything. Work the tasks **in order**; each one builds on the same
Postgres database as the last — task 02 adds history on top of task 01's
tables, task 03's star schema is populated *from* task 01/02's data, and the
capstone brings everything together. Skipping ahead means modeling
bitemporal history on top of a schema that doesn't exist yet.

## The workflow loop

Every task follows the same loop:

1. **Design** — write the DDL for that task's schema (or extend the
   existing one).
2. **Load** — write a loader that reads `data/events.jsonl` (and
   `data/clients.jsonl` where relevant) and populates it.
3. **Answer** — write one SQL file per question (`q01.sql`, `q02.sql`, ...)
   against your schema.
4. **Validate** — run `uv run python harness/validate.py --task NN` (or
   `--q q05`, or `--q q05 --file scratch.sql` to try a query before
   committing it to the real path, or `--all` once every task is done).

There are no reference solutions anywhere in this module — not in hints, not
in `.authoring/`. The validator comparing your result set against a
reference answer computed independently from the raw event stream *is* the
completion criterion. A task is done when its questions print `PASSED`
against your live database, nothing more and nothing less.

Hints escalate in three steps: `hints/hint-1.md` points in a direction with
no specifics, `hint-2.md` narrows to a specific mechanism or approach,
`hints-3.md` gets close to pseudocode. Try the task cold first — the hints
are there for when you're stuck, not as a first move.

## Generator guarantees

`harness/events.py` deterministically generates the entire event stream
(seed 42, scale 1.0 by default — do not change it, every reference answer
assumes this exact dataset) and writes it to `data/events.jsonl`, ordered by
*arrival* (`ingested_at`), not by when things actually happened. Real-world
gnarliness is baked in on purpose: ~3% of observations arrive late
(`event_time` well behind `ingested_at`), ~1% are exact duplicates arriving
twice, and admin events don't always land in the order you'd expect them to
if you assumed the world was tidy.

That said, the generator guarantees a few things your loader is allowed to
rely on:

- `shop_registered` arrives before any other event for that shop.
- `product_discovered` for a given listing arrives before that listing's
  own `price_observed` events.
- Admin events (renames, tier/attribute changes, delist/relist) arrive in
  `event_time` order relative to each other *for the same entity* — you
  won't see a shop's tier-change events out of business order, even if
  they're interleaved with other shops' events out of arrival order.
- No two distinct prices ever share the same `(shop_code, product_code,
  event_time)` — if two rows share that triple, they are the same
  observation duplicated, not two different observations that happen to
  coincide.

`data/` (including `events.jsonl`, `clients.jsonl`, `events.meta.json`, and
the cached `ground_truth.json`) is gitignored and regenerated locally —
never committed.

## Tasks

| # | Task | What it's about | Evenings |
|---|------|------------------|----------|
| 01 | relational-core | design a normalized OLTP schema from scratch (shops, products, listings, price observations) and load the event stream into it; dedup by `(shop_code, product_code, event_time)` keeping the first-arriving copy; keep both `event_time` and `ingested_at`, and the original currency | 2 |
| 02 | scd2-history | SCD Type 2 (or an equivalent interval-history design) for shop name/tier and product brand/category, backfilled from the stream; answer as-of/point-in-time questions without replaying the raw log | 1-2 |
| 03 | star-schema | Kimball-style dimensional mart in a dedicated `mart` Postgres schema — `dim_shop`, `dim_product` (both SCD2 with `valid_from`/`valid_to`), `dim_date`, `fact_price_observation` — with as-of resolution baked in at load time | 1-2 |
| 04 | capstone-bitemporal | **capstone**, three checkpoints: CP1 late-arriving data and bitemporal reasoning, CP2 lifecycle/client questions plus the full 16-question battery green in one `--all` run, CP3 a design writeup (`DESIGN.md`) | 2-3 |

Total: roughly **6-8 evenings** for the module.

## `.authoring/` is off-limits mid-task

`03-data-modeling/.authoring/` holds generation notes for whoever extends
this module later — event-stream design rationale, the exact semantics
contract, the question-to-task mapping with fixed parameters, and
verification status. It is committed (not gitignored) but it is a spoiler
file: don't read it before finishing a task, and treat "after I've
validated the task" as the earliest reasonable time to open it, if at all.

## Teardown

```bash
docker compose down -v
rm -rf data/
```
