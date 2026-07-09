"""Shared helpers for task validators in module 05.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1.
No tracebacks reach the learner.

This file is imported both from the host (uv-run validators reading Parquet
directly, e.g. via duckdb/pyarrow) and from inside the Spark container
(validators that need a live SparkSession to inspect a query plan). The
Spark-only helpers (get_plan/plan_has) import pyspark lazily so importing
this module on the host never requires pyspark to be installed.
"""

import functools
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
RAW_EVENTS_DIR = DATA_DIR / "raw-events"
REFERENCE_DIR = DATA_DIR / "reference"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

# Path as seen from inside the spark container (docker-compose mounts the
# module root at /workspace).
CONTAINER_WORKSPACE = "/workspace"

S3_ENDPOINT_IN_NETWORK = "http://minio:9000"  # from inside the compose network
S3_ACCESS_KEY = "sandbox"
S3_SECRET_KEY = "sandbox123"
S3_BUCKET = "price-lake-05"

SPARK_UI_PORT = 4040


def fail(reason):
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg=""):
    print(f"PASSED{': ' + msg if msg else ''}")
    sys.exit(0)


def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        fail(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def approx(actual, expected, rel_tol=1e-6, what="value"):
    if expected == 0:
        if abs(actual) > 1e-9:
            fail(f"{what}: expected 0, got {actual}")
        return
    if abs(actual - expected) / abs(expected) > rel_tol:
        fail(f"{what}: expected {expected}, got {actual}")


def load_learner_module(path, name):
    """Import a learner source file by path; NOT PASSED if it cannot be imported."""
    path = Path(path)
    if not path.exists():
        fail(f"missing source file {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        fail(f"could not import {path.name}: {type(e).__name__}: {e}")
    return mod


def guarded(fn):
    """Wrap a validator body so unexpected exceptions become NOT PASSED."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except SystemExit:
            raise
        except NotImplementedError:
            fail("scaffold not implemented yet (NotImplementedError)")
        except Exception as e:
            fail(f"unexpected error: {type(e).__name__}: {e}")
    return wrapper


def load_results(path, what="results"):
    path = Path(path)
    if not path.exists():
        fail(f"{what} file not found at {path} — run your measurement script first")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"{what} file at {path} is not valid JSON: {e}")


_NOTES_PLACEHOLDER = "(fill in after completing the task)"


def _is_blank_table_row(stripped):
    if not stripped.startswith("|"):
        return False
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    if not cells:
        return False
    if all(re.fullmatch(r":?-+:?", c) for c in cells):
        return True  # markdown separator row, e.g. |---|---|
    if len(cells) > 1 and all(c == "" for c in cells[1:]):
        return True  # data row with only a label filled in, rest still blank
    return False


def check_notes_filled(notes_path, min_chars=200, what="NOTES.md"):
    """Fail unless notes_path has real learner content beyond the bare template.

    Ignores markdown headers, blank lines, the "(fill in after completing the
    task)" placeholder, and empty/skeleton table rows. What remains must total
    at least min_chars of actual prose/numbers.
    """
    path = Path(notes_path)
    if not path.exists():
        fail(f"{what} not found at {path}")
    text = path.read_text(encoding="utf-8")
    content_chars = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == _NOTES_PLACEHOLDER:
            continue
        if _is_blank_table_row(stripped):
            continue
        content_chars += len(stripped)
    if content_chars < min_chars:
        fail(
            f"{what} looks unfilled: only {content_chars} chars of real content "
            f"(need >= {min_chars}). Fill in Measurements / What I learned / Gotchas / Open questions."
        )


def minio_endpoint():
    """MinIO S3 API endpoint as seen from the host (e.g. for boto3/duckdb httpfs)."""
    port = os.environ.get("SANDBOX_05_MINIO_PORT", "9501")
    return f"http://localhost:{port}"


def get_plan(df, mode="formatted"):
    """Return df.explain(mode) as a string, captured instead of printed.

    Verified against pyspark 3.5.3 inside the module-05 spark container:
    SparkSession/DataFrame.explain() only prints; there is no public
    "explain string" accessor, so this drives the same code path
    (QueryExecution.explainString) via the JVM-backed internals that
    explain() itself uses, by redirecting stdout during the call.
    """
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df.explain(mode)
    return buf.getvalue()


def plan_has(plan_text, pattern):
    """True if `pattern` (plain substring or regex) appears in a captured plan.

    Use with get_plan(), e.g.:
        plan = get_plan(joined_df, "formatted")
        plan_has(plan, "BroadcastHashJoin") and not plan_has(plan, "SortMergeJoin")
    """
    return re.search(pattern, plan_text) is not None
