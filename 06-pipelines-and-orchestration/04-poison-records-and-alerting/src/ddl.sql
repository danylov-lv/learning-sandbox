-- Given. Run this once against the warehouse before the DAG's first run:
--   docker compose exec -T warehouse psql -U sandbox -d pipelines < src/ddl.sql
--
-- staging.price_records_raw and ops.load_audit are the shared contract carried
-- over from earlier tasks in this module (create them here too, idempotently,
-- so this task is runnable on its own). ops.quarantine is new: the dead-letter
-- table this task introduces for poison and invalid records.

CREATE TABLE IF NOT EXISTS staging.price_records_raw (
    dt         date not null,
    line_no    int not null,
    payload    jsonb not null,
    loaded_at  timestamptz not null default now(),
    primary key (dt, line_no)
);

CREATE TABLE IF NOT EXISTS ops.load_audit (
    id           bigserial primary key,
    dag_id       text not null,
    run_id       text not null,
    dt           date not null,
    rows_loaded  int not null,
    status       text not null,
    finished_at  timestamptz not null default now()
);

CREATE TABLE IF NOT EXISTS ops.quarantine (
    id              bigserial primary key,
    dt              date not null,
    stage           text not null,
    reason          text not null,
    raw_line        text,
    payload         jsonb,
    quarantined_at  timestamptz not null default now()
);
