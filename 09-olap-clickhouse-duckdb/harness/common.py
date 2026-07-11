"""Shared helpers for module 09 (OLAP: ClickHouse + DuckDB) validators,
generators, and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Nothing here
requires a live stack at import time — `clickhouse_connect`, `psycopg`,
`duckdb`, and `pyarrow` are imported lazily inside the functions that
actually need them.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
PARQUET_DIR = DATA_DIR / "parquet"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

CH_DB = "price_history"
CH_USER = "sandbox"
CH_PASSWORD = "sandbox"
CH_HTTP_DEFAULT_PORT = 8309
CH_NATIVE_DEFAULT_PORT = 9309

PG_DB = "price_history"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"
PG_DEFAULT_PORT = 54309


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to module 08)
# --------------------------------------------------------------------------

def not_passed(reason):
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg=""):
    print(f"PASSED{': ' + msg if msg else ''}")
    sys.exit(0)


def guarded(fn):
    """Decorator: wrap a validator body so unexpected exceptions become
    NOT PASSED instead of a raw traceback."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SystemExit:
            raise
        except NotImplementedError:
            not_passed("scaffold not implemented yet (NotImplementedError)")
        except Exception as e:
            not_passed(f"unexpected error: {type(e).__name__}: {e}")

    return wrapper


def _last_line(text):
    """Last non-empty line of a subprocess stream or error text -- enough to
    say WHY a run failed without leaking a full traceback/stack dump."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _host():
    return os.environ.get("PGHOST", "localhost")


# --------------------------------------------------------------------------
# ClickHouse (the OLAP engine under study)
# --------------------------------------------------------------------------

def ch_http_port():
    return int(os.environ.get("SANDBOX_09_CH_HTTP_PORT", str(CH_HTTP_DEFAULT_PORT)))


def ch_native_port():
    return int(os.environ.get("SANDBOX_09_CH_NATIVE_PORT", str(CH_NATIVE_DEFAULT_PORT)))


def ch_client(database=CH_DB):
    """Live clickhouse-connect client over the HTTP interface (host localhost,
    HTTP port, user/password sandbox, db price_history), or NOT PASSED on
    failure. clickhouse-connect talks HTTP, so this uses ch_http_port(), not
    the native TCP port."""
    import clickhouse_connect

    try:
        client = clickhouse_connect.get_client(
            host=_host(),
            port=ch_http_port(),
            username=CH_USER,
            password=CH_PASSWORD,
            database=database,
        )
        client.command("SELECT 1")
        return client
    except Exception as e:
        not_passed(f"could not connect to ClickHouse on HTTP port {ch_http_port()}: {e}")


def ch_query(sql, params=None, client=None):
    """Run a SELECT and return a list of row tuples. Reuses `client` if given,
    otherwise opens a fresh one. `params` is passed through to
    clickhouse-connect as query parameters (use `{name:Type}` placeholders in
    the SQL)."""
    own = client is None
    client = client or ch_client()
    try:
        result = client.query(sql, parameters=params) if params else client.query(sql)
        return result.result_rows
    finally:
        if own:
            client.close()


def ch_command(sql, client=None):
    """Run a DDL / INSERT / SYSTEM statement (no result set). Reuses `client`
    if given, otherwise opens a fresh one."""
    own = client is None
    client = client or ch_client()
    try:
        return client.command(sql)
    finally:
        if own:
            client.close()


def ch_read_rows(sql, params=None, client=None):
    """Run `sql`, then report how many rows ClickHouse actually READ off disk
    to answer it — the structural primary-index / part-pruning signal the
    MergeTree tasks grade against.

    Contract:
      * The query is executed with a freshly generated `query_id`.
      * `SYSTEM FLUSH LOGS` forces `system.query_log` to be written.
      * We look up the row for that exact `query_id` where `type =
        'QueryFinish'` and return its `read_rows` column as an int.
      * `read_rows` is the number of rows ClickHouse scanned from granules it
        could not prune, NOT the number of rows returned. A query whose WHERE
        clause aligns with the table's ORDER BY (primary key) prunes whole
        parts/granules and reads FAR fewer rows than `count(*)`; a query that
        forces a full scan reads ~all of them. Tasks assert
        `ch_read_rows(pruned_query) < ch_read_rows(full_scan_query)` (or `<
        total_rows`) to PROVE the sparse index did its job. This is a
        structural check — it does not depend on wall-clock timing.

    Returns the int `read_rows`. NOT PASSED if the query_log row can't be
    found (e.g. logging disabled).
    """
    own = client is None
    client = client or ch_client()
    try:
        qid = f"s09-{uuid.uuid4()}"
        if params:
            client.query(sql, parameters=params, settings={"query_id": qid})
        else:
            client.query(sql, settings={"query_id": qid})
        client.command("SYSTEM FLUSH LOGS")
        rows = client.query(
            "SELECT read_rows FROM system.query_log "
            "WHERE query_id = {qid:String} AND type = 'QueryFinish' "
            "ORDER BY event_time_microseconds DESC LIMIT 1",
            parameters={"qid": qid},
        ).result_rows
        if not rows:
            not_passed(f"no system.query_log entry for query_id {qid} (is query logging on?)")
        return int(rows[0][0])
    finally:
        if own:
            client.close()


# --------------------------------------------------------------------------
# Postgres (the OLTP row-store baseline for the 50M benchmark)
# --------------------------------------------------------------------------

def pg_port():
    return int(os.environ.get("SANDBOX_09_PG_PORT", str(PG_DEFAULT_PORT)))


def pg_conninfo():
    return (
        f"host={_host()} port={pg_port()} dbname={PG_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def pg_connect():
    """Live psycopg (v3) connection to Postgres, or NOT PASSED on failure."""
    import psycopg

    try:
        return psycopg.connect(pg_conninfo())
    except psycopg.Error as e:
        not_passed(f"could not connect to Postgres on port {pg_port()}: {e}")


# --------------------------------------------------------------------------
# DuckDB (zero-server engine over the Parquet lake)
# --------------------------------------------------------------------------

def duckdb_connect():
    """In-memory DuckDB connection. No server, no file — DuckDB reads the
    Parquet lake directly via read_parquet(parquet_glob())."""
    import duckdb

    return duckdb.connect(database=":memory:")


def parquet_glob():
    """Recursive glob string for the Hive-partitioned Parquet lake, e.g.
    `.../data/parquet/**/*.parquet`. Feed to DuckDB's read_parquet(...,
    hive_partitioning=true) so the `category` partition column is exposed."""
    return str(PARQUET_DIR / "**" / "*.parquet")


# --------------------------------------------------------------------------
# Benchmark helpers (relative timing against a machine-local baseline)
# --------------------------------------------------------------------------

def time_it(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), return (result, elapsed_seconds). Wall clock
    via time.perf_counter. Timing checks are always relative to a machine-
    local baseline (see read_baseline / write_baseline), never absolute."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - start


def write_baseline(path, obj):
    """Write a machine-local baseline (e.g. reference timings) to a gitignored
    `*-local.json` file. Path may be relative to the module root."""
    p = Path(path)
    if not p.is_absolute():
        p = MODULE_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def read_baseline(path):
    """Read a machine-local baseline written by write_baseline, or None if it
    doesn't exist yet (the baseline step hasn't been run)."""
    p = Path(path)
    if not p.is_absolute():
        p = MODULE_ROOT / p
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
