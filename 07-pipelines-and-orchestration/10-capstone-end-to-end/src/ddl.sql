-- Given DDL for the capstone's mart table. Run this once against the
-- `pipelines` database (psql, a one-off Airflow task, or however you prefer)
-- before the mart-build stage of the DAG writes to it.
--
-- staging.price_records_raw, ops.load_audit, ops.quarantine and
-- core.price_records already exist from tasks 01-07 — this capstone does not
-- redefine them. This is the only new table the capstone introduces.
--
-- Grain: one row per (dt, category, currency). The mart-build stage upserts
-- this table per day-partition from core.price_records, so re-running the
-- stage for a given dt must not create duplicate rows or leave stale rows
-- from a previous run of that same dt around — plan your upsert (or
-- delete-then-insert within a transaction) accordingly.

CREATE TABLE IF NOT EXISTS mart.daily_category_prices (
    dt         date           NOT NULL,
    category   text           NOT NULL,
    currency   text           NOT NULL,
    n_records  integer        NOT NULL,
    avg_price  numeric(12,2)  NOT NULL,
    min_price  numeric(12,2)  NOT NULL,
    max_price  numeric(12,2)  NOT NULL,
    updated_at timestamptz    NOT NULL DEFAULT now(),
    PRIMARY KEY (dt, category, currency)
);
