# 02 -- Change-Event Anatomy

## Backstory

Task 01 registered a connector and watched a topic fill up. Before you can
build anything on top of that stream -- a replica table, an alert, a
derived aggregate -- you have to be able to actually read one event. Debezium
doesn't hand you a bare "price changed to 88.88"; it hands you an envelope:
`before`, `after`, `op`, a `source` block with the LSN and transaction id,
and a `ts_ms`. Learning to read that envelope correctly, for every op type
including deletes and tombstones, is the prerequisite for every later task
in this module.

There's a trap waiting inside that envelope, and it's not optional to know
about: `shop.offers.price` is `NUMERIC(12, 2)`, and under Debezium's
default `decimal.handling.mode` (`precise`), a `NUMERIC` value is not
emitted as a JSON number. It arrives as a base64 string -- the Kafka Connect
`Decimal` logical type, a two's-complement big-endian encoding of the
column's unscaled integer. If you've ever wondered why a "just read the
JSON" CDC consumer silently produced garbage prices, this is usually why.
This task makes you crack that encoding yourself, by hand, instead of
reaching for the `decimal.handling.mode=double` escape hatch.

## What's given

- `src/anatomy.py` -- a scaffold that:
  - Connects to the mart Postgres and creates+truncates
    `ops.t02_change_summary(op, n)` and `ops.t02_decoded_prices(offer_id,
    price)` -- `ensure_tables`, already written, not the point of the
    exercise.
  - Opens a manual consumer (group id fixed: `t02-anatomy`) subscribed to
    `s08.t02.shop.offers`, polling until idle for `IDLE_EXIT_SECONDS`.
  - Shows how to unwrap one message: `decode_value(msg.value())` gives you
    the payload dict, `change_op(payload)` gives you `(op, before, after)`.
  - Stops with `raise NotImplementedError` at two points: (i) tallying an
    event's `op` into `ops.t02_change_summary`, and (ii) inside
    `decode_decimal()`, the actual base64-to-Decimal conversion for
    `after["price"]`.
- The module stack: source Postgres at `localhost:54308`, mart Postgres at
  `localhost:54318`, redpanda at `localhost:19093`, Connect REST at
  `localhost:8383`. `harness/common.py` for connector lifecycle,
  `decode_value`, `change_op`, and Postgres connection helpers.

## What's required

1. In the consumer loop, for **every** non-tombstone event (snapshot `"r"`
   rows included), tally its `op` into `ops.t02_change_summary(op, n)` --
   one row per op code, `n` an exact running count.
2. Implement `decode_decimal(encoded, scale)`: given the base64 string
   found at `after["price"]` and the column's fixed scale (`PRICE_SCALE =
   2`, since `shop.offers.price` is `NUMERIC(12, 2)`), return the real
   value as a `Decimal`.
3. For every `"u"` (update) event, decode `after["price"]` and upsert
   `(offer_id, price)` into `ops.t02_decoded_prices` -- keyed by
   `after["offer_id"]`, last value wins if the same offer is updated more
   than once in a run.
4. Create both tables yourself (`CREATE TABLE IF NOT EXISTS` -- already
   wired up in `ensure_tables`, nothing to add there). The script must be
   safe to re-run: it truncates both tables at startup and rebuilds them
   from a full replay of the topic.

Try it by hand before trusting the validator:

```bash
uv run python src/anatomy.py
```

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

- Resets any leftover `s08-t02` connector/slot/publication/topics and drops
  both `ops.t02_*` tables for a clean slate; reseeds the source if its row
  counts don't match `data/ground-truth.json`.
- Registers a connector (`s08-t02`, default `decimal.handling.mode` --
  i.e. `precise`, NOT overridden) and waits for it to reach `RUNNING`.
- Applies a deterministic burst against `shop.offers` (200 inserts, 300
  updates, 100 deletes, seeded), then records each updated offer's actual
  current price straight from the source.
- Runs your `src/anatomy.py` as a subprocess and expects exit `0`.
- Asserts `ops.t02_change_summary`: `r` equals the source's total offer
  count, `c` equals 200, `u` equals 300, `d` equals 100 -- exactly.
- Asserts `ops.t02_decoded_prices`: for every updated `offer_id`, the
  decoded price equals the source's current price **exactly** -- proof the
  Decimal encoding was cracked correctly, not approximated.
- Tears down the connector, slot, publication, and topics, drops both
  `ops.t02_*` tables, and restores the source to its seeded state --
  whether the run passed or failed.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, `src/anatomy.py` is missing, the connector never reaches
`RUNNING`, your consumer exits nonzero or times out, the tally is off by
even one, or a single decoded price doesn't match exactly.

## Estimated evenings

1

## Topics to read up on

- The Debezium change-event envelope: `before` / `after` / `op` / `source`
  (`ts_ms`, `lsn`, `txId`) / top-level `ts_ms`
- Kafka Connect logical types and `decimal.handling.mode`
  (`precise` / `double` / `string`)
- Two's-complement integers and base64 encoding
- Tombstone records on delete (`tombstones.on.delete`)
