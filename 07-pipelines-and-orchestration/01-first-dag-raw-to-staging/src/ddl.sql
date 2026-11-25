-- Given schema contract for this module. Apply as-is; do not change column
-- names or types — later tasks and the validators depend on this exact shape.
--
-- Apply from the module root, e.g.:
--   cat 01-first-dag-raw-to-staging/src/ddl.sql | docker compose exec -T warehouse psql -U sandbox -d pipelines

CREATE TABLE IF NOT EXISTS staging.price_records_raw (
    dt         date        NOT NULL,
    line_no    int         NOT NULL,
    payload    jsonb       NOT NULL,
    loaded_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dt, line_no)
);

CREATE TABLE IF NOT EXISTS ops.load_audit (
    id          bigserial   PRIMARY KEY,
    dag_id      text        NOT NULL,
    run_id      text        NOT NULL,
    dt          date        NOT NULL,
    rows_loaded int         NOT NULL,
    status      text        NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT now()
);
