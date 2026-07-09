"""Loader: populates the schema from src/schema.sql from the raw event stream.

Contract:
    - Reads data/events.jsonl and data/clients.jsonl from the module root
      (03-data-modeling/data/, gitignored; regenerate with
      `uv run python harness/events.py` if missing).
    - Populates the tables created by src/schema.sql in a running Postgres
      instance at localhost:${SANDBOX_03_PORT:-54303} (db/user/pass: sandbox).
    - Must either be idempotent (safe to run twice) or clearly documented
      here as run-once, matching whatever schema.sql assumes about being
      re-run.

Performance:
    events.jsonl has 2,336,793 lines. Row-by-row INSERT will take a long
    time at this size -- use COPY (staging table + INSERT..SELECT) or
    batched inserts. Target minutes, not hours.

Run with:
    uv run python 01-relational-core/src/load.py
"""

import json  # noqa: F401
import os  # noqa: F401

import psycopg  # noqa: F401

# TODO: resolve module root / data paths (see harness/validate.py for the
#       DSN convention: postgresql://sandbox:sandbox@localhost:<port>/sandbox,
#       port from SANDBOX_03_PORT, default 54303).

# TODO: connect to Postgres.

# TODO: load data/events.jsonl into a staging table via COPY (or your chosen
#       approach) -- this is the expensive part, keep it fast.

# TODO: populate shops, products, listings from the relevant event types.

# TODO: populate price observations, deduplicating by
#       (shop_code, product_code, event_time), keeping the first-arriving
#       (smallest ingested_at) copy.

# TODO: load data/clients.jsonl into whatever table later tasks in this
#       module will need it for.

raise NotImplementedError("write the loader")
