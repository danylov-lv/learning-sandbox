"""CP1 validator for t06-capstone -- steady-state pipeline quality.

Runs `src.pipeline.run_pipeline` over the CLEAN, as-generated extraction/
classification/dedup sets (the same three sets t02/t03/t04 grade
independently) plus `src.explain.explain_product` over a handful of
deterministic product questions. Checks, in order:

  1. `require_client()` -- infra must be up before anything else is graded.
  2. `run_pipeline(...)` returns the required top-level keys, and each
     per-stage list has one entry per input item, in the SAME ORDER as the
     input (proof the pipeline processed every item, not a subset).
  3. Extraction per-field accuracy (name/brand/price/currency/in_stock)
     against gold, same style of loose match `t02` uses.
  4. Classification macro-F1 (category) and brand accuracy against gold.
  5. Dedup pairwise F1 (cluster agreement) against gold.
  6. Quality gate on CLEAN data: the quarantine rate must stay LOW -- a
     gate that quarantines a large fraction of genuinely-good records on
     well-formed input is failing the "keep good records in the clean
     catalog" requirement just as much as a gate that quarantines nothing
     would fail CP2.
  7. `explain_product` retrieval + answer quality over a small set of
     deterministic product questions.

Gold is never read from the on-disk `data/*.json` files (which are
gold-stripped) -- it is reconstructed in-memory via `generate.build_*`
against the committed `SEED`, exactly like every other task's validator in
this module.

Thresholds below were measured LIVE against qwen2.5:7b-instruct /
nomic-embed-text (Ollama, temperature=0) this authoring session -- see the
measured-vs-threshold comments above each threshold block. Set with
generous headroom for 7B sampling variance, and slightly looser than the
single-skill tasks (t02/t03/t04) since extraction errors compound into the
classification and dedup stages that consume their output... except here
each stage is graded against ITS OWN independent input set (not chained),
so the looseness reflects the pipeline's added self-assessment/gating
responsibility, not literal error compounding.

Run from the module root:

    uv run python 06-capstone/tests/validate_cp1.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import CATEGORIES, build_catalog, build_classification_set, build_dedup_set, build_extraction_set  # noqa: E402
from harness.common import DATA_DIR, guarded, macro_f1, norm_price, norm_text, not_passed, pair_f1, passed, require_client  # noqa: E402
from src.explain import explain_product  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

SEED = 151515
PRICE_TOL = 0.01
TOKEN_OVERLAP = 0.6

# -- extraction: measured live over 50/50 clean snippets this session --
#   name=1.00  brand=1.00  price=0.96  currency=1.00  in_stock=1.00
EXTRACTION_THRESHOLDS = {
    "name": 0.70,
    "brand": 0.75,
    "price": 0.65,
    "currency": 0.75,
    "in_stock": 0.70,
}

# -- classification: measured live over 80/80 clean records this session --
#   macro_f1=0.62  brand_acc=1.00 -- vs. a majority-class-constant baseline's
#   macro_f1=0.037 (verified this session), so CP1_CLASSIFY_MIN_F1 is nowhere
#   near a degenerate baseline while leaving real headroom below the
#   measured 0.62.
CP1_CLASSIFY_MIN_F1 = 0.45
CP1_CLASSIFY_MIN_BRAND_ACC = 0.70

# -- dedup: measured live over 55/55 clean items, 20 clusters this session --
#   pair_f1=1.00 -- vs. degenerate baselines verified this session:
#   all-singleton pair_f1=0.0, all-one-cluster pair_f1=0.071.
CP1_DEDUP_MIN_PAIR_F1 = 0.65

# -- quality gate on clean input: measured quarantine_rate=0.00 this session --
CP1_MAX_QUARANTINE_RATE = 0.20

# -- explain_product: measured live over 5 deterministic questions --
#   hit_rate=1.00  answer_rate=0.80
CP1_EXPLAIN_MIN_HIT_RATE = 0.60
CP1_EXPLAIN_MIN_ANSWER_RATE = 0.40
N_EXPLAIN_CANDIDATES = 20
N_EXPLAIN_QUESTIONS = 5


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


def _load_stripped(name):
    path = DATA_DIR / name
    if not path.exists():
        not_passed(f"{path} not found -- run `uv run python generate.py` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_pipeline_shape(result, extraction_items, classification_items, dedup_items):
    if not isinstance(result, dict):
        not_passed(f"run_pipeline() must return a dict, got {type(result).__name__}")
    required = {"extraction", "classification", "dedup", "catalog", "quarantine"}
    missing = required - set(result.keys())
    if missing:
        not_passed(f"run_pipeline() result is missing key(s): {sorted(missing)}")

    ext_ids = [r.get("snippet_id") for r in result["extraction"]]
    expected_ext_ids = [it["snippet_id"] for it in extraction_items]
    if ext_ids != expected_ext_ids:
        not_passed(
            "run_pipeline()['extraction'] snippet_id order/coverage doesn't match "
            "extraction_items input -- must return one entry per input, same order"
        )

    cls_ids = [r.get("record_id") for r in result["classification"]]
    expected_cls_ids = [it["record_id"] for it in classification_items]
    if cls_ids != expected_cls_ids:
        not_passed(
            "run_pipeline()['classification'] record_id order/coverage doesn't match "
            "classification_items input -- must return one entry per input, same order"
        )

    ddp_ids = [r.get("item_id") for r in result["dedup"]]
    expected_ddp_ids = [it["item_id"] for it in dedup_items]
    if ddp_ids != expected_ddp_ids:
        not_passed(
            "run_pipeline()['dedup'] item_id order/coverage doesn't match "
            "dedup_items input -- must return one entry per input, same order"
        )


def _grade_extraction(extraction_results, gold_by_id):
    scores = {k: 0 for k in EXTRACTION_THRESHOLDS}
    n = len(extraction_results)
    for r in extraction_results:
        gold = gold_by_id[r["snippet_id"]]
        if _loose_text_match(r.get("name"), gold["name"]):
            scores["name"] += 1
        if _loose_text_match(r.get("brand"), gold["brand"]):
            scores["brand"] += 1
        pred_price = norm_price(r.get("price"))
        if pred_price is not None and abs(pred_price - float(gold["price"])) <= PRICE_TOL:
            scores["price"] += 1
        pred_currency = str(r.get("currency") or "").strip().upper()
        if pred_currency == gold["currency"]:
            scores["currency"] += 1
        if isinstance(r.get("in_stock"), bool) and r.get("in_stock") == gold["in_stock"]:
            scores["in_stock"] += 1
    return {k: scores[k] / n for k in EXTRACTION_THRESHOLDS} if n else {k: 0.0 for k in EXTRACTION_THRESHOLDS}


def _grade_classification(classification_results, gold_by_id):
    preds = [r.get("category") for r in classification_results]
    golds = [gold_by_id[r["record_id"]]["gold_category"] for r in classification_results]
    f1 = macro_f1(preds, golds, CATEGORIES)
    brand_hits = sum(
        1 for r in classification_results
        if _loose_text_match(r.get("brand"), gold_by_id[r["record_id"]]["gold_brand"])
    )
    brand_acc = brand_hits / len(classification_results) if classification_results else 0.0
    return f1, brand_acc


def _grade_dedup(dedup_results, gold_by_id):
    pred_labels = [r.get("cluster_id") for r in dedup_results]
    gold_labels = [gold_by_id[r["item_id"]]["gold_cluster_id"] for r in dedup_results]
    _, _, f1 = pair_f1(pred_labels, gold_labels)
    return f1


def _explain_questions(catalog):
    """5 deterministic questions built directly from the catalog, one per
    field family, each with a small fixed candidate set (target + decoys)."""
    import numpy as np

    rng = np.random.default_rng(SEED)
    target_idx = rng.choice(len(catalog), size=N_EXPLAIN_QUESTIONS, replace=False)
    questions = []
    for i, ti in enumerate(target_idx):
        target = catalog[int(ti)]
        decoy_pool = [p for j, p in enumerate(catalog) if j != int(ti)]
        decoy_idx = rng.choice(len(decoy_pool), size=N_EXPLAIN_CANDIDATES - 1, replace=False)
        decoys = [decoy_pool[int(j)] for j in decoy_idx]
        candidates = [target] + decoys

        kind = i % 5
        if kind == 0:
            q = f"What brand is the {target['name']}?"
            gold_answer, checker = target["brand"], "text"
        elif kind == 1:
            q = f"What category is the {target['name']} in?"
            gold_answer, checker = target["category"], "text"
        elif kind == 2:
            q = f"What is the price of the {target['name']}?"
            gold_answer, checker = target["price"], "price"
        elif kind == 3:
            q = f"Is the {target['name']} in stock?"
            gold_answer, checker = target["in_stock"], "bool"
        else:
            q = f"What color is the {target['name']}?"
            gold_answer, checker = target["specs"]["color"], "text"

        questions.append({
            "question": q,
            "candidates": candidates,
            "target_product_id": target["product_id"],
            "gold_answer": gold_answer,
            "checker": checker,
        })
    return questions


def _answer_contains_fact(answer, gold_answer, checker):
    if checker == "text":
        return _loose_text_match(answer, gold_answer)
    if checker == "price":
        parsed = norm_price(answer)
        return parsed is not None and abs(parsed - float(gold_answer)) <= 0.5
    if checker == "bool":
        a = norm_text(answer)
        pos = any(w in a for w in ("yes", "in stock", "available", "true"))
        neg = any(w in a for w in ("no", "out of stock", "unavailable", "sold out", "false"))
        if gold_answer:
            return pos and not neg
        return neg and not pos
    return False


def _grade_explain(catalog, client):
    questions = _explain_questions(catalog)
    hits = 0
    answered = 0
    for q in questions:
        result = explain_product(q["question"], q["candidates"], client)
        if not isinstance(result, dict) or "answer" not in result or "citations" not in result:
            not_passed(
                f"explain_product() must return a dict with 'answer' and 'citations' keys, "
                f"got {result!r} for question {q['question']!r}"
            )
        if q["target_product_id"] in (result.get("citations") or []):
            hits += 1
        if _answer_contains_fact(result.get("answer"), q["gold_answer"], q["checker"]):
            answered += 1
    n = len(questions)
    return (hits / n if n else 0.0), (answered / n if n else 0.0)


@guarded
def main():
    client = require_client()

    extraction_items = _load_stripped("extraction.json")
    classification_items = _load_stripped("classification.json")
    dedup_items = _load_stripped("dedup.json")

    ext_gold = {it["snippet_id"]: it["gold"] for it in build_extraction_set(SEED)}
    cls_gold = {it["record_id"]: it for it in build_classification_set(SEED)}
    ddp_gold = {it["item_id"]: it for it in build_dedup_set(SEED)}
    catalog = build_catalog(SEED, 1.0)

    result = run_pipeline(extraction_items, classification_items, dedup_items, client)
    _check_pipeline_shape(result, extraction_items, classification_items, dedup_items)

    ext_acc = _grade_extraction(result["extraction"], ext_gold)
    ext_failed = [f"{k} {ext_acc[k]:.2f} < {EXTRACTION_THRESHOLDS[k]:.2f}" for k in EXTRACTION_THRESHOLDS if ext_acc[k] < EXTRACTION_THRESHOLDS[k]]

    cls_f1, brand_acc = _grade_classification(result["classification"], cls_gold)
    ddp_f1 = _grade_dedup(result["dedup"], ddp_gold)

    total_records = len(result["extraction"]) + len(result["classification"]) + len(result["dedup"])
    quarantine_rate = len(result["quarantine"]) / total_records if total_records else 1.0

    explain_hit_rate, explain_answer_rate = _grade_explain(catalog, client)

    failures = []
    if ext_failed:
        failures.append(f"extraction per-field accuracy below threshold: {'; '.join(ext_failed)}")
    if cls_f1 < CP1_CLASSIFY_MIN_F1:
        failures.append(f"classification macro-F1={cls_f1:.4f} < {CP1_CLASSIFY_MIN_F1}")
    if brand_acc < CP1_CLASSIFY_MIN_BRAND_ACC:
        failures.append(f"classification brand accuracy={brand_acc:.4f} < {CP1_CLASSIFY_MIN_BRAND_ACC}")
    if ddp_f1 < CP1_DEDUP_MIN_PAIR_F1:
        failures.append(f"dedup pair-F1={ddp_f1:.4f} < {CP1_DEDUP_MIN_PAIR_F1}")
    if quarantine_rate > CP1_MAX_QUARANTINE_RATE:
        failures.append(
            f"quarantine rate on CLEAN input={quarantine_rate:.2f} > {CP1_MAX_QUARANTINE_RATE} "
            "-- the quality gate is rejecting too many genuinely-good records"
        )
    if explain_hit_rate < CP1_EXPLAIN_MIN_HIT_RATE:
        failures.append(f"explain_product citation hit-rate={explain_hit_rate:.2f} < {CP1_EXPLAIN_MIN_HIT_RATE}")
    if explain_answer_rate < CP1_EXPLAIN_MIN_ANSWER_RATE:
        failures.append(f"explain_product answer-contains-fact rate={explain_answer_rate:.2f} < {CP1_EXPLAIN_MIN_ANSWER_RATE}")

    if failures:
        not_passed("; ".join(failures))

    summary = (
        f"extraction={ {k: round(v, 2) for k, v in ext_acc.items()} }, "
        f"classify_f1={cls_f1:.2f}, brand_acc={brand_acc:.2f}, dedup_pair_f1={ddp_f1:.2f}, "
        f"quarantine_rate={quarantine_rate:.2f}, explain_hit={explain_hit_rate:.2f}, "
        f"explain_answer={explain_answer_rate:.2f}"
    )
    passed(summary)


if __name__ == "__main__":
    main()
