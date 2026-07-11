-- Captured OLTP schema for the marketplace price DB (module 08, CDC source).
-- Debezium's Postgres connector reads this via logical decoding (pgoutput);
-- wal_level=logical, max_wal_senders and max_replication_slots are set via
-- the `source` service command in docker-compose.yml.
--
-- No publication or replication slot is created here — each task's Debezium
-- connector owns its own slot + publication (publication.autocreate.mode),
-- named per-task so tasks never collide. See .authoring/design.md.

CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.products (
    product_id BIGINT PRIMARY KEY,
    title      TEXT NOT NULL,
    category   TEXT NOT NULL,
    brand      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shop.offers (
    offer_id   BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES shop.products(product_id),
    seller     TEXT NOT NULL,
    price      NUMERIC(12, 2) NOT NULL,
    currency   TEXT NOT NULL,
    in_stock   BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX offers_product_id_idx ON shop.offers (product_id);

-- REPLICA IDENTITY FULL: without it, an UPDATE/DELETE change event's `before`
-- image only carries the primary key (the default REPLICA IDENTITY DEFAULT).
-- Downstream consumers need the full pre-image to detect which columns
-- changed (task 03) and to key deletes correctly when the PK alone isn't
-- enough context for teaching purposes. The cost is a bigger WAL footprint
-- per UPDATE/DELETE (Postgres logs the whole old row) — a deliberate
-- trade-off, documented in .authoring/design.md.
ALTER TABLE shop.products REPLICA IDENTITY FULL;
ALTER TABLE shop.offers REPLICA IDENTITY FULL;
