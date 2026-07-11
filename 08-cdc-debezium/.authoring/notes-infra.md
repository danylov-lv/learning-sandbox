# Module 08 infra build notes (wave 1)

Raw log of what was actually run to stand up and verify the module-08
foundation. `.authoring/design.md` is the polished contract; this file is
the messier "what I actually did / what broke" record for whoever resumes
this module later.

## Image tag discovery

`debezium/connect:2.7` (the tag named as an example in the brief) does not
exist on Docker Hub. Probed via `docker manifest inspect` before pulling
anything:

```
docker.io/debezium/connect:latest        -> missing
docker.io/debezium/connect:3.0           -> missing
docker.io/debezium/connect:3.1           -> missing
docker.io/debezium/connect:2.7           -> missing
docker.io/debezium/connect:2.7.3.Final   -> EXISTS
docker.io/debezium/connect:2.6           -> EXISTS
docker.io/debezium/connect:3.0.0.Final   -> EXISTS
```

Debezium tags are always the full `X.Y.Z.Final` form on Docker Hub, never
bare `X.Y`. Picked `3.0.0.Final` as current-stable. `docker pull` succeeded
cleanly, 17 layers.

## docker-compose bring-up

`docker compose up -d` from a cold state (no prior volumes/images besides
the pulled connect image) — all 5 services (`source`, `mart`, `redpanda`,
`connect`, `console`) reported healthy within ~20 seconds. Much faster than
expected for a JVM-based Kafka Connect worker; no incompatibility issues
with redpanda v24.3.5 showed up (Connect's Kafka client negotiated cleanly
against redpanda's Kafka API, `Kafka version: 3.8.0` reported client-side —
that's the bundled Connect image's Kafka client version, not redpanda's).

The `connect` healthcheck (`curl -sf http://localhost:8083/connectors`)
worked as written — `curl` is present in the `debezium/connect` image, no
substitution needed.

Verified worker envs applied by checking `GET /connectors` returned `[]`
immediately and connector registration worked on the first try, so
`CONFIG_STORAGE_TOPIC` / `OFFSET_STORAGE_TOPIC` / `STATUS_STORAGE_TOPIC` /
`GROUP_ID` were all picked up correctly from the `S{ALL_CAPS}` env-var
convention this image uses.

## Seeding

`uv run python generate.py` at default `SCALE=1.0`:

```
SCALE=1.0 n_products=5000 n_offers=20000
seeded shop.products (5000) and shop.offers (20000) in source Postgres
offers_price_sum=1884008.69 in_stock_count=17004
```

Cross-checked directly against the source via `psql`: `count(*)` on both
tables and `round(sum(price),2)` on offers all matched the script's own
printed numbers exactly.

## Probe connector

Registered `s08-probe` via `harness.common.register_connector()` +
`debezium_pg_connector_config()`. Reached RUNNING (connector + 1 task)
within about 2 seconds — logical replication startup on a 20k-row table is
fast.

Topics created automatically by the connector (verified via `rpk topic
list`): `s08.probe.shop.offers`, `s08.probe.shop.products`, plus the
worker's own `s08-connect-configs/offsets/statuses` (already existed from
worker startup, dash-prefixed not dot-prefixed — confirms the naming split
documented in design.md).

Snapshot drain: 20000 messages, all `op=r`, matched `shop.offers` row count
exactly. No surprises.

Streaming: ran one INSERT + one UPDATE + one DELETE on `shop.offers`
directly via psycopg, then re-drained the topic. Got exactly `op=c`, `op=u`
(with full old+new row thanks to `REPLICA IDENTITY FULL`), `op=d` (with full
old row), followed immediately by a tombstone (raw Kafka value `None`).

**Gotcha found: prices arrive base64-encoded.** First look at the decoded
payload showed `"price": "GSc="` instead of a plain number — not a bug,
this is Kafka Connect's `Decimal` logical type under
`decimal.handling.mode=precise` (the connector default when unset).
Verified by hand: `base64.b64decode("GSc=")` → `b"\x19'"` → unscaled int
`6439` → `/100` → `64.39`, which matched `SELECT price FROM shop.offers
WHERE offer_id=1` exactly. Decided NOT to override this in the shared
harness connector config (`decimal.handling.mode` left unset) because
decoding it is the actual point of task 02 — see design.md's "Not set:
decimal.handling.mode" section for the reasoning. Documented clearly so a
later task-authoring agent doesn't accidentally "fix" it away.

## Teardown

First teardown attempt failed:

```
psycopg.errors.ObjectInUse: replication slot "s08_probe_slot" is active for PID 170
```

immediately after `delete_connector("s08-probe")` returned `True`. Checked
`pg_replication_slots.active_pid` directly — still populated right after
connector deletion, empty a few seconds later on a second check. The
Debezium task's DB connection doesn't close synchronously with the REST
DELETE call. Retried `drop_slot()` a few seconds later — succeeded. This is
now documented in design.md as an operational gotcha (poll `active=false`
before dropping, or retry once after a short delay) since it's exactly the
kind of thing a task-04/06 validator doing automated teardown between runs
would hit.

After that: `drop_publication()` succeeded, `pg_replication_slots` confirmed
empty, `reset_topics("s08.")` deleted both probe topics and left Connect's
own bookkeeping topics alone, `list_connectors()` confirmed `[]`.

Reran `generate.py` to restore the source to stock state (the probe had
inserted offer 999001, updated offer 1, deleted offer 2). Re-verified counts
and price sum matched the original seed run exactly, and `offer_id IN
(1,2,999001)` count was back to 2 — 999001 gone, 1 and 2 restored by the
TRUNCATE+reseed.

## Final state left behind

- `docker compose up -d` stack left running (all 5 services healthy) for the
  next verification wave.
- Source: stock-seeded (5000 products, 20000 offers, matches
  `data/ground-truth.json`).
- Mart: empty schemas only, never touched.
- No connectors, no replication slots, no publications, no `s08.*` data
  topics (Connect's own internal `s08-connect-*` topics remain, which is
  expected and harmless).
- `uv.lock` committed via `uv sync` (21 packages resolved, 19 installed
  into `.venv`).

## Open items for later waves / task authors

- No task directories created yet (out of scope for this wave).
- `harness/common.py` has not been exercised by an actual pytest suite yet
  (no tests/ at module root — each task will have its own `tests/validate.py`
  importing from `harness.common`, same as module 07's layout).
- Decimal handling (`decimal.handling.mode`) is deliberately left as a task
  02 discovery, not pre-solved — don't change `debezium_pg_connector_config()`
  to add it without checking whether that undermines task 02's design.
