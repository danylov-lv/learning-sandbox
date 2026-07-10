"""Shared helpers for module 06 validators.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1. No
tracebacks reach the learner. Import this from validators that run on the
host (via `uv run`); it never requires a live Postgres connection at import
time, only when a helper that needs one is actually called.
"""

import json
import os
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"
ALERTS_PATH = DATA_DIR / "alerts" / "alerts.ndjson"

PG_DB = "pipelines"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"
PG_DEFAULT_PORT = 54306


def not_passed(reason):
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg=""):
    print(f"PASSED{': ' + msg if msg else ''}")
    sys.exit(0)


def pg_port():
    return int(os.environ.get("SANDBOX_06_PORT", str(PG_DEFAULT_PORT)))


def pg_conninfo():
    host = os.environ.get("PGHOST", "localhost")
    return (
        f"host={host} port={pg_port()} dbname={PG_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def pg_connect():
    """Return a live psycopg connection, or NOT PASSED if it can't connect."""
    import psycopg

    try:
        return psycopg.connect(pg_conninfo())
    except psycopg.Error as e:
        not_passed(f"could not connect to Postgres on port {pg_port()}: {e}")


def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def raw_day_dir(dt):
    """dt: 'YYYY-MM-DD' string. Returns data/raw/dt=YYYY-MM-DD/."""
    return RAW_DIR / f"dt={dt}"


def raw_day_file(dt):
    return raw_day_dir(dt) / "prices.ndjson"


def all_raw_days():
    """Sorted list of 'YYYY-MM-DD' strings present under data/raw/."""
    if not RAW_DIR.exists():
        return []
    days = []
    for child in RAW_DIR.iterdir():
        if child.is_dir() and child.name.startswith("dt="):
            days.append(child.name[len("dt="):])
    return sorted(days)


def read_alerts():
    """Read data/alerts/alerts.ndjson (written by the alert-sink container)
    as a list of parsed JSON objects. Returns [] if the file doesn't exist
    yet (e.g. no alert has fired). Lines that fail to parse are skipped.
    """
    if not ALERTS_PATH.exists():
        return []
    alerts = []
    for line in ALERTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            alerts.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return alerts


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
