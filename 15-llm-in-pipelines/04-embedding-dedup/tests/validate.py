"""Validator for 15-llm-in-pipelines task 04 -- embedding-dedup.

Loads `data/dedup.json` (the gold-stripped title-variant list) and calls
the learner's `cluster_items(items, client)` in `src/dedup.py`. Gold
cluster ids are never read from disk -- they come from calling
`generate.build_dedup_set(SEED)` directly and keying by `item_id`, exactly
like every other validator in this module.

Grading uses `harness.common.pair_f1`: for every one of the C(n,2) item
pairs, does the pair fall in the same cluster under the learner's
partition vs. under gold. A single threshold, `PAIR_F1_THRESHOLD`,
measured live against `qwen2.5:7b-instruct`'s embedding sibling
(`nomic-embed-text`) while authoring this task:

  - A connected-components clustering over cosine similarity, at any
    threshold in the wide gap between this dataset's measured intra-
    cluster cosine (min ~0.885) and inter-cluster cosine (max ~0.858),
    scores pair_f1 in the 0.90-1.00 range.
  - The two degenerate baselines both score far below that: "every item
    is its own cluster" scores pair_f1 = 0.0 (zero recall -- no true
    duplicate pair is ever grouped), "every item is one cluster" scores
    pair_f1 ~= 0.07 (zero precision headroom -- 1430 false-positive pairs
    swamp the handful of true ones).

`PAIR_F1_THRESHOLD = 0.75` sits with generous headroom below a correct
clustering's measured range and well above both degenerate baselines, so
a reasonable choice of similarity threshold or clustering method passes
without requiring a near-perfect partition.

Run from the module root:

    uv run python 04-embedding-dedup/tests/validate.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import DATA_DIR, guarded, not_passed, pair_f1, passed, require_client  # noqa: E402
from generate import SEED, build_dedup_set  # noqa: E402
from src.dedup import cluster_items  # noqa: E402

PAIR_F1_THRESHOLD = 0.75


def load_items():
    path = DATA_DIR / "dedup.json"
    if not path.exists():
        not_passed(f"data/dedup.json not found at {path} -- run `uv run python generate.py` first")
    return json.loads(path.read_text(encoding="utf-8"))


@guarded
def main():
    client = require_client()

    items = load_items()
    gold_by_id = {it["item_id"]: it["gold_cluster_id"] for it in build_dedup_set(SEED)}

    pred = cluster_items(items, client)

    if not isinstance(pred, dict):
        not_passed(f"cluster_items() must return a dict mapping item_id -> cluster_label, got {type(pred).__name__}")

    item_ids = [it["item_id"] for it in items]
    missing = [iid for iid in item_ids if iid not in pred]
    if missing:
        not_passed(f"cluster_items() result is missing {len(missing)} item_id(s), e.g. {missing[:5]}")

    pred_labels = [pred[iid] for iid in item_ids]
    gold_labels = [gold_by_id[iid] for iid in item_ids]

    precision, recall, f1 = pair_f1(pred_labels, gold_labels)

    if f1 < PAIR_F1_THRESHOLD:
        not_passed(
            f"pair_f1={f1:.4f} (precision={precision:.4f}, recall={recall:.4f}) is below the "
            f"required {PAIR_F1_THRESHOLD} -- check your embedding similarity threshold and "
            f"clustering logic. (For reference: an all-singleton partition and an all-one-"
            f"cluster partition both score far below this bar -- neither is a valid solution.)"
        )

    passed(f"pair_f1={f1:.4f} (precision={precision:.4f}, recall={recall:.4f}), required >= {PAIR_F1_THRESHOLD}")


if __name__ == "__main__":
    main()
