# 01 -- Connector Setup: Snapshot vs Streaming

## Backstory

You inherited a marketplace price database. Up to now, keeping downstream
systems in sync meant polling `shop.offers` on an interval and diffing
against whatever was seen last time -- a request spent even when nothing
changed, and always at least one interval behind reality.

The database itself already knows about every change the moment it
commits: that's what its write-ahead log is. Change Data Capture means
reading that log instead of re-querying the table. Debezium is a Kafka
Connect plugin that turns Postgres's logical replication stream into a
Kafka topic per table -- one JSON event per insert/update/delete, no
polling, no missed intervals.

Before any of that is useful you have to stand the connector up and
understand what it actually does the moment it starts. A brand-new
Debezium Postgres connector runs in two distinct phases against a table
that already has rows in it:

1. **Snapshot** -- it reads every existing row once and emits it as a
   change event with `op="r"` ("read"), so a consumer starting from zero
   ends up with the full current state without you having to bulk-load it
   separately.
2. **Streaming** -- once the snapshot is done, it switches to consuming the
   replication slot live, emitting `op="c"/"u"/"d"` for every insert,
   update, and delete that happens on the source from that point on.

This task is about registering a connector and proving to yourself, from
the event stream alone, that both phases really happened and that the
handoff between them is real.

## What's given

- `src/register.py` -- a scaffold with:
  - `main()`, already written: calls your `build_config()`, registers the
    result via `harness.common.register_connector()`, waits for the
    connector to reach `RUNNING` via `wait_for_connector_running()`, prints
    a confirmation, and exits `0`.
  - `build_config()` -- stops at `raise NotImplementedError`. This is the
    one thing you write: the Debezium Postgres connector definition dict
    for this task.
- The stack from the module README: source Postgres at `localhost:54308`
  (db `shop`, tables `shop.offers` / `shop.products`, seeded by
  `uv run python generate.py`), Kafka Connect REST API at
  `localhost:8383`, redpanda at `localhost:19093`.
- `harness/common.py` -- `register_connector()`, `connector_status()`,
  `wait_for_connector_running()`, `delete_connector()`, `drain()`,
  `change_op()`, `kafka_bootstrap()`, `source_connect()`. Note:
  `debezium_pg_connector_config()` also exists in there, but it's the
  *validator's* helper for building throwaway probe connectors elsewhere in
  this module -- importing it here would skip the actual exercise, so
  `build_config()` must construct its own dict.

## What's required

Fill in `build_config()` to return a connector definition shaped like
`{"name": ..., "config": {...}}`, ready to hand to `register_connector()`.

The per-task naming convention (see the module README) fixes these values
for this task:

- connector name: `s08-t01`
- `slot.name`: `s08_t01_slot`
- `publication.name`: `s08_t01_pub`
- `topic.prefix`: `s08.t01` (so events land on `s08.t01.shop.offers` and
  `s08.t01.shop.products`)

Beyond naming, your config needs to tell Debezium: which connector plugin
to run (`io.debezium.connector.postgresql.PostgresConnector`), how to
reach the source (`database.hostname=source` -- the in-network Docker
Compose service name, not `localhost`; `database.port=5432`;
`database.user`/`database.password=sandbox`; `database.dbname=shop`),
which Postgres logical-decoding plugin to use (`plugin.name=pgoutput` --
the built-in Postgres 10+ output plugin, no extension install needed),
that the publication should auto-create itself scoped to just the tables
you list (`publication.autocreate.mode=filtered`), which tables to capture
(`table.include.list`, a comma-separated `schema.table` string covering
both `shop.offers` and `shop.products`), and which snapshot behavior you
want on first start (`snapshot.mode=initial` -- snapshot then stream; look
up what the other modes mean while you're at it).

CLI/behavior contract the validator drives against:

- Run with `uv run python src/register.py` from this task's directory.
- Reads no arguments, no stdin.
- Registers connector `s08-t01` and exits `0` once it reaches `RUNNING`
  (both the connector and its one task).
- Exits nonzero (via `harness.common.not_passed`, called internally by
  `wait_for_connector_running`/`register_connector` on failure) if
  registration fails or the connector never comes up -- you don't need to
  handle that yourself, the given plumbing already does.
- Safe to run more than once: `register_connector` PUTs to
  `/connectors/<name>/config`, which is idempotent.

A note on prices: this task only counts events, it never reads
`price`. You don't need to decode anything -- that's task 02. If you want
readable prices while poking around in Redpanda Console, you're free to
add `decimal.handling.mode=double` to your config; it isn't required and
the validator doesn't check for it.

## Completion criteria

Run `uv run python tests/validate.py` from this task's directory. It:

1. Tears down any leftover `s08-t01` connector/slot/publication/topics from
   a previous attempt.
2. Checks the source is seeded (`shop.offers` row count matches
   `data/ground-truth.json`); tells you to run `uv run python generate.py`
   if not.
3. Runs your `src/register.py` as a subprocess and expects exit `0`.
4. Confirms the connector reaches `RUNNING`.
5. **Snapshot check**: drains `s08.t01.shop.offers` and
   `s08.t01.shop.products` from the beginning and counts `op="r"` events --
   must equal the source row counts exactly.
6. **Streaming check**: applies one insert, one update, and one delete
   directly against `shop.offers`, then drains the offers topic again and
   confirms `op="c"`, `op="u"`, and `op="d"` all show up, and that the
   update's event carries a non-null `before` image (proving
   `REPLICA IDENTITY FULL` is doing its job).
7. Tears everything down again and reseeds the source, leaving the stack
   clean for the next task.

Fails gracefully (`NOT PASSED: <reason>`, exit 1, no traceback) if the
stack is down, the source isn't seeded, `src/register.py` errors out or
never reaches `RUNNING`, the snapshot counts don't match, or the streaming
ops don't show up.

## Estimated evenings

1

## Topics to read up on

- Logical decoding & the `pgoutput` plugin
- Debezium snapshot vs streaming phases (and what the other `snapshot.mode`
  values mean)
- Replication slots & publications
- Kafka Connect REST connector lifecycle (register, status, states)
- Change-event `op` codes (`r`/`c`/`u`/`d`) and tombstones
