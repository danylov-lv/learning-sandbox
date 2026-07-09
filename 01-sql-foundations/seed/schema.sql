-- Schema for module 01-sql-foundations: price-intelligence scraping warehouse.
-- Tables only; FKs and secondary indexes are added after COPY (see post_load.sql).

DROP TABLE IF EXISTS price_snapshots CASCADE;
DROP TABLE IF EXISTS exchange_rates CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS sources CASCADE;

CREATE TABLE sources (
    id       INT PRIMARY KEY,
    name     TEXT NOT NULL,
    country  TEXT NOT NULL,
    tier     SMALLINT NOT NULL,      -- 1 = major marketplace, 2 = mid, 3 = long tail
    currency TEXT NOT NULL           -- local pricing currency for this source
);

CREATE TABLE categories (
    id        INT PRIMARY KEY,
    name      TEXT NOT NULL,
    parent_id INT,
    level     SMALLINT NOT NULL      -- 0 = root .. 3 = leaf
);

CREATE TABLE products (
    id            INT PRIMARY KEY,
    name          TEXT NOT NULL,
    category_id   INT NOT NULL,
    brand         TEXT NOT NULL,
    first_seen_at DATE NOT NULL
);

CREATE TABLE price_snapshots (
    id          BIGINT PRIMARY KEY,
    product_id  INT NOT NULL,
    source_id   INT NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    price       NUMERIC(12,2) NOT NULL,
    currency    TEXT NOT NULL,
    in_stock    BOOLEAN NOT NULL
);

CREATE TABLE exchange_rates (
    currency    TEXT NOT NULL,
    rate_date   DATE NOT NULL,
    rate_to_usd NUMERIC(12,6) NOT NULL,   -- amount_in_currency * rate_to_usd = amount_in_usd
    PRIMARY KEY (currency, rate_date)
);
