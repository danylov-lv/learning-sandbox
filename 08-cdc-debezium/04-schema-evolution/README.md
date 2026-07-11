# 04 -- Schema Evolution

## Backstory

Task 03 got you a materializer that keeps a mart table in sync with
`shop.offers` by applying `before`/`after` diffs and tombstones correctly.
It works great -- right up until the source team ships a migration:

```sql
ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2);
```

Nobody paged you. Nobody stopped the connector. The replication slot kept
streaming, pgoutput kept publishing, and the very next change event on
`shop.offers` simply has one more key in its `after` object than the last
one did. Whether your consumer notices or dies right there depends entirely
on how it was written.

A brittle consumer hardcodes what it expects: a fixed tuple of columns, a
literal `after["discount_pct"]` access, an INSERT statement built from a
column list baked in at authoring time. The first post-migration event
either KeyErrors or silently drops a field it doesn't know to look for. A
robust consumer treats every after-image as "whatever fields happen to be
there right now" and reads defensively -- `after.get("discount_pct")`,
not `after["discount_pct"]` -- so an old-shape event and a new-shape event
on the same topic, in the same run, both just work.

This task is about writing that second kind of consumer, and proving it
survives the migration live: the validator applies real traffic before the
`ALTER TABLE`, runs the `ALTER TABLE` for real against the running
connector, applies more real traffic after it, and checks your mart table
converges exactly with the source in both regimes -- without you ever
touching your consumer's code in between.

## What's given

- `src/materialize.py` -- a scaffold that:
  - `ensure_replica_table`, already written: creates
    `replica.offers(offer_id, product_id, seller, price, currency,
    in_stock, discount_pct)` if it doesn't exist. Note `discount_pct` is
    nullable and created UP FRONT, before the source even has the column --
    the replica schema is made forward-compatible ahead of the migration
    on purpose.
  - A consumer loop, already written: subscribes to
    `s08.t04.shop.offers`, decodes each message via
    `harness.common.decode_value` / `change_op`, skips tombstones, and
    calls your `apply_change` for every real change event, committing the
    Kafka offset right after.
  - `apply_change(conn, op, before, after)` -- stops at
    `raise NotImplementedError`. This is what you write.
- The stack from the module README: source Postgres at `localhost:54308`
  (`shop.offers`), mart Postgres at `localhost:54318` (db `mart`, schema
  `replica`), Kafka Connect REST at `localhost:8383`, redpanda at
  `localhost:19093`.
- `harness/common.py` -- `mart_connect()`, `kafka_bootstrap()`,
  `decode_value()`, `change_op()`.

## What's required

Fill in `apply_change`:

- `op` is `'r'`, `'c'`, or `'u'` -> upsert `replica.offers` keyed by
  `after["offer_id"]` with `product_id`, `seller`, `price`, `currency`,
  `in_stock`, and `discount_pct` from `after`. Read `discount_pct` via
  `after.get("discount_pct")` -- `None` when the key is absent, which is
  true for every event published before the source's `ADD COLUMN` and
  would be true for any other future column this code doesn't know about
  yet. `after["discount_pct"]` (plain indexing) is exactly the bug this
  task exists to catch.
- `op` is `'d'` -> delete the row for `before["offer_id"]`
  (`shop.offers` has `REPLICA IDENTITY FULL`, so `before` is a full
  pre-image, not just the primary key).
- Use `ON CONFLICT (offer_id) DO UPDATE` for the upsert and a plain
  idempotent `DELETE ... WHERE offer_id = ...` -- every event carries the
  full current row, so reapplying the same event twice must leave
  `replica.offers` unchanged.
- Do NOT special-case the `ALTER TABLE` itself. There is no DDL event to
  react to here -- an additive column change on a table already covered by
  a `pgoutput` publication just starts appearing in `after`, automatically.
  The only code that needs to change is how defensively you read the
  dict, and you only have to write that once.

CLI/behavior contract the validator drives against:

- Run with `uv run python src/materialize.py` from this task's directory.
- Fixed consumer group id `t04-materializer`.
- Reads `s08.t04.shop.offers`, maintains `replica.offers`.
- Exits `0` once idle for 10 seconds (caught up with the topic).
- Safe to run repeatedly, including immediately after the source's schema
  changed mid-run -- rerunning must never crash and must converge.

Try it by hand before trusting the validator (needs a registered `s08-t04`
connector on `shop.offers` -- the validator normally does this for you,
but you can register one yourself via `harness.common` if you want to poke
around first):

```bash
uv run python src/materialize.py   # converges the pre-DDL state
# ... simulate the migration: ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2);
#     then do a few more inserts/updates, some setting discount_pct, some not ...
uv run python src/materialize.py   # must NOT crash; converges again, including discount_pct
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

1. Tears down any leftover `s08-t04` connector/slot/publication/topics and
   drops `replica.offers` for a clean slate.
2. Defensively drops `discount_pct` from `shop.offers` if a previous
   interrupted run left it there, and checks the source is seeded (tells
   you to run `uv run python generate.py` if not).
3. Registers connector `s08-t04` on `shop.offers` (with
   `decimal.handling.mode=double`, so `price`/`discount_pct` arrive as
   plain JSON numbers) and waits for `RUNNING`.
4. Runs your `materialize.py`, then asserts `replica.offers` matches
   `shop.offers` on every column except `discount_pct` -- which must still
   be `NULL` everywhere, since the source doesn't have the column yet.
5. Runs `ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2)` for
   real, then drives a deterministic burst against the running connector:
   300 inserts, 600 updates, 100 deletes (`build_workload(seed=4, ...)`),
   plus explicit `discount_pct` writes on the new rows and on a fixed
   sample of pre-existing ones.
6. Runs your `materialize.py` again. **Must exit 0** -- a crash here means
   the consumer isn't reading the after-image defensively.
7. Asserts `replica.offers` matches `shop.offers` **exactly**, including
   `discount_pct` (`NULL` where the source is `NULL`, matching value
   within `0.01` where it's set).
8. Restores `shop.offers` to its stock schema, tears the connector down,
   and reseeds the source, leaving the stack clean for the next task.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the source isn't seeded, `materialize.py` errors out or
crashes on the post-DDL run, or `replica.offers` doesn't converge exactly.

## Estimated evenings

1-2

## Topics to read up on

- Additive vs breaking schema changes (`ADD COLUMN` vs `DROP COLUMN` /
  type changes / renames) and why only some of them are safe to ship
  without coordinating with every consumer first
- How a Postgres publication and `pgoutput` propagate a new column to an
  already-running logical replication slot with no explicit DDL event
- Forward-compatible vs backward-compatible consumer design
- Defensive deserialization: reading a dict via `.get()` with a default
  instead of indexing or assuming a fixed shape
- Schema registries (the concept -- Avro/Protobuf plus a compatibility
  mode) and why this module's plain-JSON envelopes don't need one
