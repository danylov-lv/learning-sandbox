CREATE TABLE offers (
    source text NOT NULL,
    sku text NOT NULL,
    PRIMARY KEY (source, sku)
);

CREATE TABLE observations (
    source text NOT NULL,
    sku text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    cents integer NOT NULL CHECK (cents > 0),
    PRIMARY KEY (source, sku, version),
    FOREIGN KEY (source, sku) REFERENCES offers
);

CREATE TABLE current_prices (
    source text NOT NULL,
    sku text NOT NULL,
    version integer NOT NULL,
    cents integer NOT NULL CHECK (cents > 0),
    PRIMARY KEY (source, sku),
    FOREIGN KEY (source, sku, version) REFERENCES observations
);

CREATE TABLE source_notes (
    source text NOT NULL,
    sku text NOT NULL,
    body text NOT NULL CHECK (length(body) > 0),
    PRIMARY KEY (source, sku),
    FOREIGN KEY (source, sku) REFERENCES offers
);

CREATE TABLE stock (
    sku text PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE allocations (
    worker text PRIMARY KEY,
    units integer NOT NULL CHECK (units >= 0)
);

CREATE TABLE processed_batches (
    batch_id text PRIMARY KEY
);

INSERT INTO offers (source, sku)
SELECT source, sku
FROM unnest(ARRAY['market', 'outlet', 'direct']) AS sources(source)
CROSS JOIN unnest(ARRAY['a', 'b', 'c', 'd']) AS products(sku);
