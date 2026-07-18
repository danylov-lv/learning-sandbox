"""Shared helpers for module 14 (stats and ML foundations) validators,
generators, and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. This module
is pure Python — there is no docker stack for module 14 — but every
third-party import (numpy, pandas, pyarrow, matplotlib) is still lazy inside
the function that needs it, so importing `harness.common` never has side
effects.

Three helper families here map onto the module's three task arcs:

- **Ground truth / observations loading** (`load_ground_truth`,
  `load_observations`): the shared scraped-price dataset built once by
  `generate.py` and consumed by all 13 tasks.
- **Numeric comparison** (`approx`, `check_close`): float/money comparisons
  for stats-task validators — never exact-decimal equality on money.
- **Plot structure check** (`require_figure`): confirms a matplotlib Figure
  was actually drawn into (axes with artists), for tasks whose deliverable is
  a chart. Visual correctness itself is human-checked; this is the
  machine-checkable floor.
- **Timing baseline** (`time_it` / `write_baseline` / `read_baseline`):
  relative-to-machine timing, same semantics as module 11, used by the
  vectorization-speedup task and any ML timing comparison.
"""

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"
OBSERVATIONS_PATH = DATA_DIR / "observations.parquet"


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to module 11)
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


# --------------------------------------------------------------------------
# Benchmark helpers (relative timing against a machine-local baseline)
# --------------------------------------------------------------------------

def time_it(fn, *args, **kwargs):
    """Call fn(*args, **kwargs), return (result, elapsed_seconds). Wall clock
    via time.perf_counter. Timing checks are always relative to a machine-
    local baseline (see read_baseline / write_baseline), never absolute."""
    import time

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
# Dataset loading
# --------------------------------------------------------------------------

def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


def load_observations():
    """Read the shared observations dataset into a pandas DataFrame (via
    pyarrow), or NOT PASSED if it hasn't been generated yet."""
    if not OBSERVATIONS_PATH.exists():
        not_passed(f"observations not found at {OBSERVATIONS_PATH} — run `uv run python generate.py` first")

    import pandas as pd

    return pd.read_parquet(OBSERVATIONS_PATH, engine="pyarrow")


# --------------------------------------------------------------------------
# Numeric comparison (float/money — never exact-decimal equality)
# --------------------------------------------------------------------------

def approx(a, b, rel=1e-6, abs_=1e-9):
    """True if a and b agree within a relative-or-absolute tolerance."""
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b)))


def check_close(name, got, want, rel=1e-6, abs_=1e-9):
    """Return (ok, msg) comparing got vs. want under `approx`. `msg` explains
    the mismatch (or confirms the match) using `name` for context."""
    ok = approx(got, want, rel=rel, abs_=abs_)
    if ok:
        return True, f"{name}: {got!r} ~= {want!r}"
    return False, f"{name}: got {got!r}, want {want!r} (rel={rel}, abs={abs_})"


# --------------------------------------------------------------------------
# Plot structure check (visual correctness is human-checked; this is the
# machine-checkable floor: a figure exists and axes actually have artists)
# --------------------------------------------------------------------------

def require_figure(fig, min_axes=1):
    """Given a matplotlib Figure, verify it structurally: is a Figure, has
    >= min_axes Axes, and at least one of those axes actually contains
    drawn artists (lines, patches, collections, or images) rather than
    being blank. Returns (ok, msg)."""
    import matplotlib.figure

    if not isinstance(fig, matplotlib.figure.Figure):
        return False, f"expected a matplotlib Figure, got {type(fig).__name__}"

    axes = fig.get_axes()
    if len(axes) < min_axes:
        return False, f"figure has {len(axes)} axes, need >= {min_axes}"

    has_artists = any(
        len(ax.lines) or len(ax.patches) or len(ax.collections) or len(ax.images)
        for ax in axes
    )
    if not has_artists:
        return False, "figure axes contain no drawn artists (lines/patches/collections/images) — looks blank"

    return True, f"figure ok: {len(axes)} axes with drawn artists"
