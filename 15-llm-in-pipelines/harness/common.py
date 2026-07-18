"""Shared helpers for module 15 (LLMs in pipelines) validators, generators,
and task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Every
third-party import (numpy) is lazy inside the function that needs it, so
importing `harness.common` never has side effects.

Two helper families beyond the module-11/14 plumbing (`not_passed`,
`passed`, `guarded`, `_last_line`, `load_ground_truth`, `write_baseline`,
`read_baseline`):

- **`require_client`**: probes the configured provider before a validator
  trusts any LLM-dependent check, so a learner sees "Ollama isn't running"
  rather than a confusing metric failure when the infra just isn't up.
- **Metrics** (`prf_from_sets`, `accuracy`, `macro_f1`, `pair_f1`,
  `norm_price`, `norm_text`): pure functions every task 02-06 validator
  reuses instead of re-deriving precision/recall/F1/clustering-agreement
  arithmetic per task.
"""

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"
CORPUS_DIR = DATA_DIR / "corpus"


# --------------------------------------------------------------------------
# Pass / fail plumbing (identical semantics to modules 10/11/14)
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

def write_baseline(path, obj):
    """Write a machine-local baseline to a gitignored `*-local.json` file.
    Path may be relative to the module root."""
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
# Ground truth loading
# --------------------------------------------------------------------------

def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# LLM client readiness (distinguishes infra-not-ready from wrong-solution)
# --------------------------------------------------------------------------

def require_client():
    """Probe the configured provider before any LLM-dependent validator
    trusts its output. For the default ("ollama") provider: GET {base}/api/tags
    must succeed and both LLM_MODEL and LLM_EMBED_MODEL must be present in the
    tag list. On failure, calls not_passed(...) with an actionable message
    (never a bare connection-refused traceback). On success, returns a ready
    LLMClient via get_client()."""
    import os

    import httpx

    from harness.llm import DEFAULT_EMBED_MODEL, DEFAULT_MODEL, DEFAULT_OLLAMA_BASE_URL, get_client

    provider = (os.environ.get("LLM_PROVIDER") or "ollama").lower()

    if provider == "ollama":
        base_url = (os.environ.get("LLM_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        model = os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        embed_model = os.environ.get("LLM_EMBED_MODEL") or DEFAULT_EMBED_MODEL
        try:
            resp = httpx.get(f"{base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
        except Exception as e:
            not_passed(
                f"Ollama not reachable at {base_url} ({type(e).__name__}: {e}) — "
                f"run `docker compose up -d` in this module, then "
                f"`docker compose exec ollama ollama pull {model}` and "
                f"`docker compose exec ollama ollama pull {embed_model}`"
            )
        names = {m.get("name", "").split(":")[0] for m in resp.json().get("models", [])}
        missing = [m for m in (model, embed_model) if m.split(":")[0] not in names]
        if missing:
            not_passed(
                f"Ollama reachable at {base_url} but missing model(s) {missing} — "
                f"run `docker compose exec ollama ollama pull " + " ".join(missing) + "`"
            )
    # openai provider: presence of an API key is the readiness signal; the
    # first live call surfaces auth/network errors on its own.
    elif provider == "openai" and not os.environ.get("LLM_API_KEY"):
        not_passed("LLM_PROVIDER=openai but LLM_API_KEY is not set")

    return get_client()


# --------------------------------------------------------------------------
# Metrics (pure; numpy where useful)
# --------------------------------------------------------------------------

def prf_from_sets(pred: set, gold: set):
    """Precision, recall, F1 of `pred` against `gold` (set membership)."""
    if not pred and not gold:
        return 1.0, 1.0, 1.0
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def accuracy(preds: list, golds: list) -> float:
    if len(preds) != len(golds):
        raise ValueError(f"length mismatch: {len(preds)} preds vs {len(golds)} golds")
    if not preds:
        return 0.0
    return sum(p == g for p, g in zip(preds, golds)) / len(preds)


def macro_f1(preds: list, golds: list, labels: list) -> float:
    """Unweighted mean of per-label F1 (one-vs-rest), matching sklearn's
    `f1_score(average="macro")` semantics. A label with no gold and no
    predicted instances contributes F1 = 1.0 (vacuously correct)."""
    if len(preds) != len(golds):
        raise ValueError(f"length mismatch: {len(preds)} preds vs {len(golds)} golds")
    f1s = []
    for label in labels:
        pred_set = {i for i, p in enumerate(preds) if p == label}
        gold_set = {i for i, g in enumerate(golds) if g == label}
        _, _, f1 = prf_from_sets(pred_set, gold_set)
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def pair_f1(pred_labels: list, gold_labels: list):
    """Clustering pairwise F1: precision/recall/F1 of "same-cluster" pair
    agreement between `pred_labels` and `gold_labels` (parallel lists of
    cluster ids, one entry per item, same order). A pair (i, j), i < j,
    counts as a positive in a labeling iff pred/gold_labels[i] ==
    pred/gold_labels[j]."""
    import numpy as np

    n = len(pred_labels)
    if len(gold_labels) != n:
        raise ValueError(f"length mismatch: {len(pred_labels)} pred vs {len(gold_labels)} gold labels")
    if n < 2:
        return 1.0, 1.0, 1.0

    pred_arr = np.asarray(pred_labels)
    gold_arr = np.asarray(gold_labels)
    pred_same = pred_arr[:, None] == pred_arr[None, :]
    gold_same = gold_arr[:, None] == gold_arr[None, :]
    iu = np.triu_indices(n, k=1)
    pred_same = pred_same[iu]
    gold_same = gold_same[iu]

    tp = int(np.sum(pred_same & gold_same))
    pred_pos = int(np.sum(pred_same))
    gold_pos = int(np.sum(gold_same))

    if pred_pos == 0 and gold_pos == 0:
        return 1.0, 1.0, 1.0
    precision = tp / pred_pos if pred_pos else 0.0
    recall = tp / gold_pos if gold_pos else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def norm_price(s):
    """Parse a loosely-formatted price string into a float, or None if it
    doesn't look like a price at all.

    Handles: a leading currency symbol ($/€/£) or trailing currency code
    (USD/EUR/GBP), thousands separators as either comma ("1,299.00") or dot
    in a European-style grouping ("1.299,00"), a bare comma decimal
    ("19,99" -> 19.99), surrounding whitespace, and stray non-numeric
    characters elsewhere in the string. Returns None for empty/unparseable
    input (e.g. "N/A", "", "call for price").
    """
    import re

    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)

    text = str(s).strip()
    if not text:
        return None

    # Strip a trailing currency code (case-insensitive) and any symbols,
    # keep digits, comma, dot, leading minus.
    text = re.sub(r"(?i)\b(usd|eur|gbp)\b", "", text)
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None

    neg = text.startswith("-")
    text = text.lstrip("-")

    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        # Whichever separator appears last is the decimal point.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma and not has_dot:
        # A single comma with exactly 2 trailing digits is a decimal comma
        # ("19,99"); anything else (or multiple commas) is thousands
        # grouping ("1,299").
        parts = text.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
    # has_dot-only, or neither: already parseable as-is.

    try:
        value = float(text)
    except ValueError:
        return None
    return -value if neg else value


def norm_text(s) -> str:
    """Lowercase, strip, collapse internal whitespace, drop punctuation --
    for loose string matching (e.g. comparing extracted vs. gold titles
    where formatting may differ but content shouldn't)."""
    import re

    if s is None:
        return ""
    text = str(s).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
