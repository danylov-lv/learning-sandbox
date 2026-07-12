"""Shared helpers for module 10 (NoSQL patterns: Redis + MongoDB + Postgres
JSONB) validators, generators, and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Nothing here
requires a live stack at import time — `redis`, `pymongo`, and `psycopg` are
imported lazily inside the functions that actually need them.

The three services are SHARED across the module's 8 tasks. To keep parallel
validation collision-free, each task confines its state to a namespace:
Redis keys under `s10:tNN:`, Mongo collections prefixed `tNN_`, and (task 06)
a Postgres schema `t06`. Validators clean their OWN namespace on setup
(redis_flush_prefix / drop_collection / DROP SCHEMA) and never FLUSHALL.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"
PRODUCTS_PATH = DATA_DIR / "products.json"
EVENTS_PATH = DATA_DIR / "events.json"

REDIS_DEFAULT_PORT = 6310
MONGO_DEFAULT_PORT = 27310
PG_DEFAULT_PORT = 54310

MONGO_USER = "sandbox"
MONGO_PASSWORD = "sandbox"
MONGO_DEFAULT_DB = "sandbox"

PG_DB = "sandbox"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to module 09)
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
# Redis (rate limiter, lock, dedup, streams — tasks 01-04 and the capstone)
# --------------------------------------------------------------------------

def redis_port():
    return int(os.environ.get("SANDBOX_10_REDIS_PORT", str(REDIS_DEFAULT_PORT)))


def redis_client(decode_responses=True):
    """Live redis.Redis (host localhost, redis_port(), no password), pinged on
    connect, or NOT PASSED on failure. `decode_responses=True` by default so
    string commands return `str`; pass False for byte-exact work (Bloom, raw
    stream payloads)."""
    import redis

    try:
        client = redis.Redis(
            host=_host(),
            port=redis_port(),
            decode_responses=decode_responses,
        )
        client.ping()
        return client
    except Exception as e:
        not_passed(f"could not connect to Redis on port {redis_port()}: {e}")


def redis_flush_prefix(client, prefix):
    """DEL every key matching `prefix + "*"` via SCAN (non-blocking, cursor
    based) so a task can reset its OWN namespace without FLUSHDB — the Redis
    instance is shared across all tasks. Returns the number of keys deleted."""
    deleted = 0
    for key in client.scan_iter(match=f"{prefix}*", count=500):
        client.delete(key)
        deleted += 1
    return deleted


# --------------------------------------------------------------------------
# MongoDB (document modeling, mongo-vs-jsonb, capstone materialization)
# --------------------------------------------------------------------------

def mongo_port():
    return int(os.environ.get("SANDBOX_10_MONGO_PORT", str(MONGO_DEFAULT_PORT)))


def mongo_uri():
    return (
        f"mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{_host()}:{mongo_port()}/"
        f"?authSource=admin"
    )


def mongo_client():
    """Live pymongo MongoClient authenticated against the admin DB, pinged on
    connect, or NOT PASSED on failure."""
    import pymongo

    try:
        client = pymongo.MongoClient(mongo_uri(), serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client
    except Exception as e:
        not_passed(f"could not connect to MongoDB on port {mongo_port()}: {e}")


def mongo_db(name=MONGO_DEFAULT_DB):
    """The `sandbox` Database on a fresh authenticated client."""
    return mongo_client()[name]


# --------------------------------------------------------------------------
# Postgres (the JSONB side of task 06)
# --------------------------------------------------------------------------

def pg_port():
    return int(os.environ.get("SANDBOX_10_PG_PORT", str(PG_DEFAULT_PORT)))


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
# Concurrency helper (tasks 01/02 hammer the rate limiter / lock)
# --------------------------------------------------------------------------

def run_concurrently(fn, n_workers, per_worker=1, *, args_factory=None):
    """Run `fn` across a ThreadPoolExecutor of `n_workers` threads, each thread
    calling `fn` `per_worker` times (so `n_workers * per_worker` total calls).

    If `args_factory` is given it is called as `args_factory(worker_idx,
    call_idx)` and must return a tuple of positional args for that call;
    otherwise `fn` is called with no arguments.

    Returns a flat list of every call's return value, ordered by
    (worker_idx, call_idx) — deterministic regardless of thread scheduling.

    Exception policy: any exception raised inside a call is captured and the
    FIRST one (in worker/call order) is re-raised after all threads finish, so
    a concurrency bug surfaces as a real error rather than being swallowed.
    """
    results = [None] * (n_workers * per_worker)
    errors = [None] * (n_workers * per_worker)

    def _worker(worker_idx):
        for call_idx in range(per_worker):
            slot = worker_idx * per_worker + call_idx
            try:
                if args_factory is not None:
                    args = args_factory(worker_idx, call_idx)
                    results[slot] = fn(*args)
                else:
                    results[slot] = fn()
            except Exception as e:  # noqa: BLE001 - captured, re-raised in order below
                errors[slot] = e

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        list(pool.map(_worker, range(n_workers)))

    for err in errors:
        if err is not None:
            raise err
    return results


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
