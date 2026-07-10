-- Given DDL for task 05.
--
-- staging.price_records_raw and ops.quarantine are the shared contract carried
-- over from earlier tasks in this module (raw ingest and dead-letter store) —
-- they are repeated here as IF NOT EXISTS so this file is safe to run
-- standalone against a fresh warehouse. core.price_records is NEW: it is
-- the boundary this task's contract gate writes across.
--
-- Run once against the warehouse, e.g.:
--   docker compose exec -T warehouse psql -U sandbox -d pipelines -f - < src/ddl.sql

CREATE TABLE IF NOT EXISTS staging.price_records_raw (
    dt        date NOT NULL,
    line_no   integer NOT NULL,
    payload   jsonb NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dt, line_no)
);

CREATE TABLE IF NOT EXISTS ops.quarantine (
    id             bigserial PRIMARY KEY,
    dt             date NOT NULL,
    stage          text NOT NULL,
    reason         text NOT NULL,
    raw_line       text,
    payload        jsonb,
    quarantined_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.price_records (
    dt            date NOT NULL,
    source_site   text NOT NULL,
    product_url   text NOT NULL,
    title         text NOT NULL,
    category      text NOT NULL,
    price         numeric(12, 2) NOT NULL,
    currency      text NOT NULL,
    in_stock      boolean NOT NULL,
    scraped_at    timestamptz NOT NULL,
    seller_rating real,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_site, product_url, scraped_at)
);
