"""Validator for 15-llm-in-pipelines task 03 -- classification-and-enrichment.

Loads `data/classification.json` (80 gold-stripped records) and calls the
learner's `classify_record(title, description, client)` from
`src/classify.py` once per record, live against the configured LLM
provider. Gold (`gold_category`, `gold_brand`) is never read from the
on-disk file -- it is reconstructed by calling `build_classification_set`
directly with the module's committed SEED, keyed by `record_id`, mirroring
every other validator in this module.

Two metrics:

  - PRIMARY: `macro_f1` of predicted vs. gold category over the 8-label
    closed set. A predicted category is normalized (stripped, lowercased)
    before comparison; anything that doesn't map onto one of the 8 known
    labels is treated as wrong (never matched) rather than excused or
    dropped from scoring.
  - SECONDARY: brand-extraction accuracy -- `norm_text(predicted_brand) ==
    norm_text(gold_brand)` fraction over all 80 records.

Thresholds (`MACRO_F1_THRESHOLD`, `BRAND_ACC_THRESHOLD`) were measured live
against `qwen2.5:7b-instruct` at `temperature=0` while authoring this task
and set with headroom below that measurement -- see the module's
`.authoring/design.md` (task 03 section) for the exact numbers and the
degenerate-baseline check (a constant/majority-category prediction must
fail MACRO_F1_THRESHOLD; verified during authoring, not by this file).

Run from the module root:

    uv run python 15-llm-in-pipelines/03-classification-and-enrichment/tests/validate.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import SEED, build_classification_set  # noqa: E402
from harness.common import guarded, macro_f1, norm_text, not_passed, passed, require_client  # noqa: E402
from src.classify import CATEGORIES, classify_record  # noqa: E402

DATA_PATH = MODULE_ROOT / "data" / "classification.json"

# Measured while authoring against qwen2.5:7b-instruct at temperature=0, two
# independent reference prompts: category macro_f1 ~0.57-0.68, brand accuracy
# ~0.975-0.99 (see .authoring/design.md task 03 section for the exact runs).
# The majority-category constant baseline measured macro_f1 ~0.037 on this
# data (macro-F1 collapses every non-majority label's F1 to 0) -- thresholds
# below are set with generous headroom above that baseline and below the
# measured LLM scores, to tolerate a reasonable prompt design and run-to-run
# sampling variance without requiring a heavily-tuned prompt.
MACRO_F1_THRESHOLD = 0.42
BRAND_ACC_THRESHOLD = 0.75


def _normalize_category(raw):
    if not isinstance(raw, str):
        return None
    norm = raw.strip().lower()
    return norm if norm in CATEGORIES else None


@guarded
def main():
    client = require_client()

    if not DATA_PATH.exists():
        not_passed(f"data file not found at {DATA_PATH} -- run `uv run python generate.py` first")

    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if not records:
        not_passed(f"{DATA_PATH} is empty")

    gold_by_id = {item["record_id"]: item for item in build_classification_set(SEED)}

    pred_categories = []
    gold_categories = []
    brand_correct = 0
    brand_total = 0

    for record in records:
        record_id = record.get("record_id")
        gold = gold_by_id.get(record_id)
        if gold is None:
            not_passed(f"record_id {record_id!r} from {DATA_PATH.name} not found in build_classification_set output")

        result = classify_record(record["title"], record["description"], client)
        if not isinstance(result, dict):
            not_passed(
                f"classify_record({record_id!r}, ...) must return a dict, got {type(result).__name__}: {result!r}"
            )

        category = _normalize_category(result.get("category"))
        pred_categories.append(category if category is not None else "")
        gold_categories.append(gold["gold_category"])

        brand_total += 1
        pred_brand_norm = norm_text(result.get("brand"))
        if pred_brand_norm and pred_brand_norm == norm_text(gold["gold_brand"]):
            brand_correct += 1

    f1 = macro_f1(pred_categories, gold_categories, labels=CATEGORIES)
    brand_acc = brand_correct / brand_total if brand_total else 0.0

    if f1 < MACRO_F1_THRESHOLD:
        not_passed(
            f"category macro_f1={f1:.4f} below required {MACRO_F1_THRESHOLD} -- "
            f"check that the prompt states the closed category list explicitly and "
            f"that the model's category output is being parsed/normalized correctly"
        )

    if brand_acc < BRAND_ACC_THRESHOLD:
        not_passed(
            f"brand accuracy={brand_acc:.4f} below required {BRAND_ACC_THRESHOLD} "
            f"(category macro_f1={f1:.4f} did pass) -- check that the extracted brand "
            f"is the literal token from the title, not a paraphrase or a guessed "
            f"category-appropriate brand"
        )

    passed(
        f"category macro_f1={f1:.4f} (>= {MACRO_F1_THRESHOLD}), "
        f"brand accuracy={brand_acc:.4f} (>= {BRAND_ACC_THRESHOLD}), n={len(records)}"
    )


if __name__ == "__main__":
    main()
