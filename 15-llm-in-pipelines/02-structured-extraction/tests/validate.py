"""Validator for 15-llm-in-pipelines task 02 -- structured-extraction.

Loads `data/extraction.json` (50 gold-STRIPPED HTML snippets), calls the
learner's `extract_fields(html, client)` from `src/extract.py` once per
snippet, and compares the returned fields to gold. Gold is never read from
the stripped data file -- it is reconstructed in-memory by calling
`generate.build_extraction_set(SEED)` directly (the same builder
`generate.py` used to write the stripped file), keyed by `snippet_id`, so a
learner's own code touching the on-disk file can never become the oracle.

Per-field comparison:
  - price: the learner's returned value is parsed with
    `harness.common.norm_price` (handles floats, numeric strings, stray
    currency symbols) and compared to the gold float with an absolute
    tolerance (PRICE_TOL). An unparseable/missing price counts as wrong.
  - currency: uppercased exact string match against gold ("USD"/"EUR"/"GBP").
  - in_stock: exact bool match (truthy/falsy coercion is NOT accepted --
    the contract asks for a real bool).
  - name / brand: loose match via `harness.common.norm_text` -- normalized
    exact match, OR (since a 7B model may rephrase/reorder tokens or drop a
    model number) at least TOKEN_OVERLAP fraction of the gold's normalized
    tokens appear in the prediction's normalized tokens. This is
    deliberately forgiving: the lesson is "did the model find the right
    brand/name," not exact string reproduction.

Run from the module root:

    uv run python 02-structured-extraction/tests/validate.py

Thresholds (below) were measured live against qwen2.5:7b-instruct at
temperature=0 (the harness default) over all 50 snippets; see the
measured-vs-threshold comment above THRESHOLDS for the actual run. Set with
generous headroom below the measured numbers per the module's calibration
philosophy (7B model + CUDA/llama.cpp batching nondeterminism means
temperature=0 is not bit-identical run to run).
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import build_extraction_set  # noqa: E402
from harness.common import DATA_DIR, guarded, norm_price, norm_text, not_passed, passed, require_client  # noqa: E402
from src.extract import extract_fields  # noqa: E402

SEED = 151515

PRICE_TOL = 0.01
TOKEN_OVERLAP = 0.6

# Measured live against qwen2.5:7b-instruct (Ollama, temperature=0) over all
# 50 snippets in data/extraction.json, two independent runs this authoring
# session (identical both times):
#   name=1.00  brand=1.00  price=0.96  currency=1.00  in_stock=1.00
# Thresholds set with generous headroom below each measured value for 7B
# sampling variance across machines/driver versions (temperature=0 is not
# bit-identical run to run due to CUDA/llama.cpp batching nondeterminism).
THRESHOLDS = {
    "name": 0.85,
    "brand": 0.85,
    "price": 0.80,
    "currency": 0.85,
    "in_stock": 0.85,
}

REQUIRED_KEYS = {"name", "brand", "price", "currency", "in_stock"}


def _loose_text_match(pred, gold) -> bool:
    p, g = norm_text(pred), norm_text(gold)
    if not g:
        return False
    if p == g:
        return True
    p_tokens, g_tokens = set(p.split()), set(g.split())
    if not p_tokens or not g_tokens:
        return False
    overlap = len(p_tokens & g_tokens) / len(g_tokens)
    return overlap >= TOKEN_OVERLAP


@guarded
def main():
    client = require_client()

    data_path = DATA_DIR / "extraction.json"
    if not data_path.exists():
        not_passed(f"{data_path} not found -- run `uv run python generate.py` first")

    import json

    snippets = json.loads(data_path.read_text(encoding="utf-8"))
    gold_by_id = {item["snippet_id"]: item["gold"] for item in build_extraction_set(SEED)}

    scores = {k: 0 for k in REQUIRED_KEYS}
    n = 0

    for snippet in snippets:
        snippet_id = snippet["snippet_id"]
        gold = gold_by_id.get(snippet_id)
        if gold is None:
            not_passed(f"snippet_id {snippet_id!r} from data/extraction.json has no matching gold record")

        result = extract_fields(snippet["html"], client)
        if not isinstance(result, dict):
            not_passed(
                f"extract_fields() must return a dict, got {type(result).__name__} for snippet {snippet_id!r}"
            )
        missing = REQUIRED_KEYS - set(result.keys())
        if missing:
            not_passed(f"extract_fields() result for {snippet_id!r} is missing key(s): {sorted(missing)}")

        n += 1

        if _loose_text_match(result.get("name"), gold["name"]):
            scores["name"] += 1
        if _loose_text_match(result.get("brand"), gold["brand"]):
            scores["brand"] += 1

        pred_price = norm_price(result.get("price"))
        if pred_price is not None and abs(pred_price - float(gold["price"])) <= PRICE_TOL:
            scores["price"] += 1

        pred_currency = str(result.get("currency") or "").strip().upper()
        if pred_currency == gold["currency"]:
            scores["currency"] += 1

        pred_in_stock = result.get("in_stock")
        if isinstance(pred_in_stock, bool) and pred_in_stock == gold["in_stock"]:
            scores["in_stock"] += 1

    if n == 0:
        not_passed("data/extraction.json contained no snippets")

    accuracy = {k: scores[k] / n for k in REQUIRED_KEYS}

    failed = [f"{k} {accuracy[k]:.2f} < {THRESHOLDS[k]:.2f}" for k in REQUIRED_KEYS if accuracy[k] < THRESHOLDS[k]]
    if failed:
        summary = ", ".join(f"{k}={accuracy[k]:.2f}" for k in REQUIRED_KEYS)
        not_passed(f"per-field accuracy below threshold over {n} snippets ({summary}) -- failing: {'; '.join(failed)}")

    summary = ", ".join(f"{k}={accuracy[k]:.2f}" for k in REQUIRED_KEYS)
    passed(f"per-field accuracy over {n} snippets: {summary}")


if __name__ == "__main__":
    main()
