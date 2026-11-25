# DESIGN

Fill in each section with your own reasoning, once you've built the schema
and made the tradeoffs. Bullets are prompts to answer, not a checklist.

## Schema overview

- Final schema, in words or ASCII: OLTP, SCD2 history, `mart` star schema.
- Which tables are sources of truth vs. derived/rebuildable?

## Normalization decisions

- Where did you denormalize on purpose, and what did it buy you?
- Where did you keep normalization even though it cost you a join?

## History: SCD2 vs event replay

- Per entity (shop, product, listing): which approach, and why that one?
- What does each approach cost — storage, write path, query complexity?

## Bitemporality

- How are `event_time` and `ingested_at` stored and used?
- What predicate(s) reproduce a report published on some past date D?

## What breaks at 100x

- 2.3M -> 230M observations: what's the first thing that stops working?
- What would you change before it breaks, not after?

## If I started over

- One modeling decision from tasks 01-04 you'd make differently, and why?
