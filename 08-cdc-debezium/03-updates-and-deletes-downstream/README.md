# 03 -- Updates and Deletes Downstream

## Backstory

Task 01 watched a connector's snapshot hand off to streaming. Task 02
picked apart one change event's envelope by hand. Neither task built
anything that stays useful after you stop looking at it.

A downstream service that needs marketplace offers -- a search index, a
pricing dashboard, a recommendation job -- should not query the OLTP
database for every read. That is exactly the load pattern logical
replication exists to avoid: instead, it wants its own always-current copy
of `shop.offers`, fed by the same change stream you've been decoding, and
it wants that copy correct all the time, not just right after a fresh
snapshot. Sellers restock, reprice, and delist constantly; the replica has
to track every one of those without you rerunning a full snapshot.

This is the core exercise of consuming CDC for real: three event shapes
(snapshot rows, updates, deletes) collapse into two operations against a
table (upsert, delete), and the tricky part is not writing the SQL -- it's
writing it so that re-consuming an event you've already applied (Kafka
redelivery, or you rerunning your own script) never leaves the replica in
a different state than a clean run would have.

## What's given

- `src/materialize.py` -- a scaffold that:
  - Opens a mart Postgres connection and creates
    `replica.offers(offer_id PRIMARY KEY, product_id, seller, price,
    currency, in_stock, updated_at)` if it doesn't exist -- `ensure_replica_table`,
    already written, not the point of the exercise. Same column set as
    `shop.offers` on the source.
  - Opens a manual-commit consumer on group `t03-materializer`, subscribed
    to `s08.t03.shop.offers`.
  - Runs an idle-exit loop: after `IDLE_EXIT_SECONDS` (~10s) with no new
    message, it commits offsets, closes cleanly, and exits `0` -- this is
    how the validator knows a run has caught up rather than hanging
    forever waiting for a topic that has gone quiet.
  - Decodes each message with `harness.common.decode_value` /
    `change_op`, giving you `(op, before, after)` per event, and skips
    tombstones (`decode_value(msg.value())` is `None`) without touching
    the replica.
  - Stops with `raise NotImplementedError` at the one place that matters:
    applying a single change event to `replica.offers`.
  - **Note on prices**: the validator registers this task's connector with
    `decimal.handling.mode=double`, so `after["price"]` (and
    `before["price"]`) arrive here as a plain JSON number, not the
    base64-encoded `Decimal` bytes task 02 made you decode by hand. That
    decoding exercise was task 02's point, not this one's -- here you can
    just use the number.
- The stack from the module README: source Postgres at `localhost:54308`
  (db `shop`), mart Postgres at `localhost:54318` (db `mart`, schema
  `replica` pre-created), redpanda at `localhost:19093`, Kafka Connect
  REST at `localhost:8383`, `harness/common.py` for connection/topic/
  connector helpers.
- The validator registers your connector for you (name `s08-t03`, slot
  `s08_t03_slot`, publication `s08_t03_pub`, `topic.prefix` `s08.t03` ->
  topic `s08.t03.shop.offers`) -- you are not writing connector
  registration code in this task, only the consumer that reads the
  resulting topic.

## What's required

1. Fill in the loop body in `src/materialize.py`: for each decoded event,
   apply it to `replica.offers` according to its `op`:
   - `op` is `'r'` (snapshot row) or `'c'` (insert): upsert the row from
     `after` (`INSERT ... ON CONFLICT (offer_id) DO UPDATE`).
   - `op` is `'u'` (update): upsert the row from `after`, same as above --
     an update and an insert both mean "this offer now looks like `after`",
     so they can share one upsert.
   - `op` is `'d'` (delete): delete the row identified by `before`'s
     `offer_id`. There is no `after` on a delete.
   - Tombstone (decoded payload is `None`): skip. Already handled by the
     given plumbing before your code runs.
2. The upsert and the delete both need to be safe to run twice. Kafka is
   at-least-once; re-running `materialize.py` from scratch after a partial
   run, or a redelivered message, must never leave `replica.offers` in a
   state a clean single run wouldn't have produced.
3. CLI/behavior contract the validator drives against:
   - Run with `uv run python src/materialize.py` from this task's
     directory.
   - Fixed consumer group id `t03-materializer`.
   - Reads `s08.t03.shop.offers` (from the beginning -- the connector's
     `snapshot.mode=initial` means the topic starts with one `op=r` event
     per existing source row), maintains `replica.offers`.
   - Exits `0` once idle for `IDLE_EXIT_SECONDS` (caught up with the
     topic).
   - Safe to run repeatedly, including resuming after a previous run
     already left partial state in `replica.offers` -- the validator runs
     it once against the initial snapshot, applies a burst of
     inserts/updates/deletes to the source, then runs it a second time and
     expects the same table it would get from one continuous run.

Try it by hand before trusting the validator:

```bash
uv run python src/materialize.py   # first run: replica.offers fills from the snapshot
uv run python src/materialize.py   # rerun with nothing new: idle-exits immediately, table unchanged
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Clean-slates task 03's connector, slot, publication, topic, and
  `replica.offers` table.
- Ensures the source is seeded (regenerates it if not).
- Registers the `s08-t03` connector (with `decimal.handling.mode=double`)
  and waits for it to finish its snapshot.
- Runs your `materialize.py` to idle-exit, then asserts `replica.offers`
  matches `shop.offers` exactly: same set of `offer_id`s, matching
  `product_id`/`seller`/`currency`/`in_stock` per row, `price` within
  `0.01`.
- Applies a deterministic burst of inserts, updates, and deletes to the
  source via `generate.py`'s `build_workload`, waits for the change stream
  to catch up, then runs your `materialize.py` a second time (a resume,
  not a fresh start).
- Asserts `replica.offers` matches `shop.offers` exactly again: new offers
  present, updated offers reflect their new price/stock, deleted offers
  are gone.
- Tears everything down afterward (connector, slot, publication, topic,
  `replica.offers`) and restores the source to its stock seed.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, `src/materialize.py` is missing, a run times out, or the
replica doesn't converge with the source after either phase.

## Estimated evenings

1

## Topics to read up on

- Log-based replication vs snapshot polling
- Upsert / merge semantics (`INSERT ... ON CONFLICT DO UPDATE`)
- Tombstones and delete handling in a change-data-capture stream
- At-least-once delivery and idempotent apply
- Replica convergence: what it means for a downstream copy to provably
  equal its source
