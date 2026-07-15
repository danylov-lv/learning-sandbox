"""Shared helpers for module 12 (API engineering: FastAPI over a clean
marketplace DB, Postgres + Redis) validators, generators, and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Nothing here
requires a live stack at import time -- psycopg, psycopg_pool, redis, and
tracemalloc are imported lazily inside the functions that actually need them.

The Postgres `shop` schema and the Redis instance are SHARED across the
module's 9 tasks + capstone, all of which may run in parallel. No task may
write to `shop` (it is a read-only seeded corpus); a task needing writable
state creates its own `tNN` Postgres schema and namespaces its Redis keys
under `s12:tNN:`. See .authoring/design.md for the full namespacing contract.
"""

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

PG_DEFAULT_PORT = 54312
REDIS_DEFAULT_PORT = 6312

PG_DB = "sandbox"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"

SHOP_SCHEMA = "shop"

# Canonical corpus seed -- the single source of truth for both generate.py's
# numpy RNG stream and this module's deterministic password-salt derivation.
# generate.py imports this rather than redefining it, so the two can never
# drift apart.
SEED = 121212

# scrypt cost parameters for the fixture password hashes stored in
# shop.users.password_hash. These are deliberately LOW (n=1024, not the
# security-grade 2**14+ recommended for real login systems) -- see
# design.md's "Fixture passwords" section: hashing 20,000 users at
# generation time must stay inside a couple of minutes, and this is seed
# data for exercises, not a security posture. Never treat these params as a
# security recommendation.
SCRYPT_N = 1024
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to modules 08/09/10/11)
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
    """Write a machine-local baseline (e.g. reference timings/RPS) to a
    gitignored `*-local.json` file. Path may be relative to the module root."""
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


# --------------------------------------------------------------------------
# Async execution
# --------------------------------------------------------------------------

def run_async(coro):
    """Run `coro` to completion via `asyncio.run` and return its result. If a
    loop is already running in this thread, NOT PASSED with a clear message
    instead of raising asyncio's own RuntimeError."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        not_passed(
            "run_async() called from inside a running event loop — "
            "await the coroutine directly instead of calling run_async()"
        )


# --------------------------------------------------------------------------
# Memory measurement
# --------------------------------------------------------------------------

def measure_peak_memory(fn, *args, **kwargs):
    """Run fn(*args, **kwargs) under tracemalloc and return
    (result, peak_bytes) -- the peak TRACED allocation observed during the
    call, not RSS. Used for task 05 (streaming exports): a peak-ratio check
    (streaming vs naive-materialize-then-serialize) against a small
    constant, never an absolute byte count.

    fn is called as-is (sync). To measure async code, pass a zero-arg lambda
    that itself calls run_async(...) or drives its own event loop --
    measure_peak_memory does not start one for you.
    """
    import tracemalloc

    tracemalloc.start()
    try:
        result = fn(*args, **kwargs)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


# --------------------------------------------------------------------------
# Postgres (the shared read-only `shop` corpus; per-task `tNN` schemas)
# --------------------------------------------------------------------------

def pg_port():
    return int(os.environ.get("SANDBOX_12_PG_PORT", str(PG_DEFAULT_PORT)))


def pg_dsn():
    return (
        f"host={_host()} port={pg_port()} dbname={PG_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def pg_conn():
    """Live psycopg (v3) connection, or NOT PASSED on failure. Usable as a
    context manager (psycopg.Connection supports `with` natively)."""
    import psycopg

    try:
        return psycopg.connect(pg_dsn())
    except psycopg.Error as e:
        not_passed(f"could not connect to Postgres on port {pg_port()}: {e}")


def pg_pool(min_size=1, max_size=10, **kwargs):
    """Open a psycopg_pool.ConnectionPool against the module's Postgres, or
    NOT PASSED on failure. Callers are responsible for closing it (it's a
    context manager: `with pg_pool() as pool: ...`), e.g. task 09's load
    test and task 04's background-worker connection reuse."""
    from psycopg_pool import ConnectionPool

    try:
        pool = ConnectionPool(
            pg_dsn(), min_size=min_size, max_size=max_size, open=False, **kwargs
        )
        pool.open(wait=True, timeout=10)
        return pool
    except Exception as e:
        not_passed(f"could not open a Postgres connection pool on port {pg_port()}: {e}")


# --------------------------------------------------------------------------
# Redis (per-task namespaced under s12:tNN:)
# --------------------------------------------------------------------------

def redis_port():
    return int(os.environ.get("SANDBOX_12_REDIS_PORT", str(REDIS_DEFAULT_PORT)))


def redis_client(decode_responses=True):
    """Live redis.Redis (host localhost, redis_port(), no password), pinged
    on connect, or NOT PASSED on failure."""
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
    based) so a task can reset its OWN namespace without FLUSHALL/FLUSHDB --
    the Redis instance is shared across every task running in parallel.
    Returns the number of keys deleted."""
    deleted = 0
    for key in client.scan_iter(match=f"{prefix}*", count=500):
        client.delete(key)
        deleted += 1
    return deleted


# --------------------------------------------------------------------------
# Fixture passwords (shop.users.password_hash)
# --------------------------------------------------------------------------

def build_password(user_id):
    """Pure function of user_id -- the plaintext fixture password for a
    seeded user. Documented rule (see design.md): `pw-<id>-kupitron`. This is
    fixture data for exercises (JWT auth, login flows), NOT a security
    claim -- never reuse this pattern for real credentials."""
    return f"pw-{int(user_id)}-kupitron"


def _password_salt(user_id):
    """Deterministic per-user salt derived from the corpus SEED, so reruns
    of generate.py produce byte-identical password_hash values."""
    return hashlib.sha256(f"{SEED}:user:{int(user_id)}".encode()).digest()[:16]


def hash_password(password, salt):
    """scrypt-hash `password` under `salt` (bytes), returning the stored
    string format `scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>`."""
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    """Verify `password` against a `stored` value produced by hash_password.
    Returns False (never raises) on a malformed stored value."""
    try:
        algo, n_s, r_s, p_s, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    computed = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(computed, expected)


def build_user_password_hash(user_id):
    """Convenience: the exact stored password_hash for a seeded user id,
    computed the same way generate.py computed it. Useful for validators
    that want to log in as a known seeded user without querying the DB."""
    return hash_password(build_password(user_id), _password_salt(user_id))
