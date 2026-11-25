"""CP2 validator for t06-capstone -- chaos / graceful degradation.

Feeds `src.pipeline.run_pipeline` a HOSTILE variant of the steady-state
input: a deterministic subset of the extraction HTML snippets is truncated/
garbled (simulating a scraper bug), AND the client passed to the pipeline
is wrapped so a fraction of `generate`/`chat` calls return clearly-invalid,
non-JSON junk instead of delegating to the real model (simulating a
degraded/misbehaving model backend) -- `embed` is left untouched, so the
dedup stage runs on clean input throughout. This chaos generation is this
capstone task's own responsibility (per `.authoring/design.md`'s
"out of scope for this generator" note), not something `generate.py`
produces.

This checkpoint does NOT re-check CP1's accuracy bars -- it checks
GRACEFUL DEGRADATION:

  1. `run_pipeline(...)` must not raise (a crash is caught by `@guarded`
     and reported as NOT PASSED, same as any other unexpected exception).
  2. `run_pipeline(...)` must still return the required shape (one entry
     per stage per input, same order) even with corrupted/junked calls
     mixed in.
  3. Among records that landed in the CLEAN CATALOG (extraction +
     classification stages), the fraction that are actually correct vs.
     independently-recomputed gold ("catalog precision") must stay
     reasonably high -- the gate must not be waving obviously-wrong
     records through.
  4. Among records that are actually wrong vs. gold, the fraction that
     landed in QUARANTINE ("quarantine recall") must clear a floor -- the
     gate must be doing real work, not a no-op that quarantines nothing.
  5. Quarantine is non-empty (the gate actually engaged) and catalog is
     non-empty (good records still made it through) -- a pipeline that
     dumps EVERYTHING into quarantine also fails this checkpoint, since
     that isn't graceful degradation either.

Thresholds are deliberately looser than CP1's -- see the measured-vs-
threshold comment above the threshold block, calibrated LIVE this
authoring session including against a no-op-gate baseline (everything
routed to catalog, nothing quarantined) to confirm CP2 actually
distinguishes a real gate from a fake one.

Run from the module root:

    uv run python 06-capstone/tests/validate_cp2.py
"""

import json
import random
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from generate import build_classification_set, build_dedup_set, build_extraction_set  # noqa: E402
from harness.common import DATA_DIR, guarded, norm_price, norm_text, not_passed, passed, prf_from_sets, require_client  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

SEED = 151515
CHAOS_SEED = 271828
PRICE_TOL = 0.01
TOKEN_OVERLAP = 0.6

HTML_CORRUPT_FRACTION = 0.35
JUNK_CALL_RATE = 0.15
JUNK_TEXT = "##!! not json at all -- service degraded, try again later !!##"

# -- measured live this session against qwen2.5:7b-instruct/nomic-embed-text
#    under the chaos conditions above, over the 130 extraction+classification
#    records (18/50 html snippets corrupted, 17/130 generate/chat calls
#    junked): a reference confidence gate measured catalog_precision=0.752,
#    quarantine_recall=0.537; a NO-OP gate (route everything to catalog,
#    simulated by treating every record as correct-by-default) measured
#    catalog_precision=0.585 on this SAME run's underlying correctness
#    counts -- CP2_MIN_CATALOG_PRECISION sits above that no-op number so a
#    fake/near-no-op gate can't slip through, with headroom below the
#    reference gate's measured value.
CP2_MIN_CATALOG_PRECISION = 0.65
CP2_MIN_QUARANTINE_RECALL = 0.35


class _JunkyClient:
    """Wraps a real LLMClient; a deterministic fraction of generate/chat
    calls return clearly-invalid, non-JSON text instead of delegating.
    `embed` always delegates -- dedup stays on clean input."""

    def __init__(self, inner, junk_rate, seed):
        self._inner = inner
        self._junk_rate = junk_rate
        self._rng = random.Random(seed)
        self.call_count = 0
        self.junk_count = 0

    def _maybe_junk(self, fallback):
        self.call_count += 1
        if self._rng.random() < self._junk_rate:
            self.junk_count += 1
            return JUNK_TEXT
        return fallback()

    def generate(self, *args, **kwargs):
        return self._maybe_junk(lambda: self._inner.generate(*args, **kwargs))

    def chat(self, *args, **kwargs):
        return self._maybe_junk(lambda: self._inner.chat(*args, **kwargs))

    def embed(self, *args, **kwargs):
        return self._inner.embed(*args, **kwargs)

    @property
    def model(self):
        return self._inner.model

    @property
    def embed_model(self):
        return self._inner.embed_model


def _corrupt_html(html, rng):
    """Truncate the snippet at a random point (30%-70% of its length) --
    simulates a scraper that cut off mid-response. May or may not destroy
    any given field depending on where the cut lands."""
    cut = rng.uniform(0.3, 0.7)
    n = max(10, int(len(html) * cut))
    return html[:n]


def _load_stripped(name):
    path = DATA_DIR / name
    if not path.exists():
        not_passed(f"{path} not found -- run `uv run python generate.py` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _loose_text_match(pred, gold) -> bool:
    p, g = norm_text(pred), norm_text(gold)
    if not g:
        return False
    if p == g:
        return True
    p_tokens, g_tokens = set(p.split()), set(g.split())
    if not p_tokens or not g_tokens:
        return False
    return len(p_tokens & g_tokens) / len(g_tokens) >= TOKEN_OVERLAP


def _extraction_correct(record, gold):
    return (
        _loose_text_match(record.get("name"), gold["name"])
        and _loose_text_match(record.get("brand"), gold["brand"])
        and (lambda p: p is not None and abs(p - float(gold["price"])) <= PRICE_TOL)(norm_price(record.get("price")))
        and str(record.get("currency") or "").strip().upper() == gold["currency"]
        and isinstance(record.get("in_stock"), bool)
        and record.get("in_stock") == gold["in_stock"]
    )


def _classification_correct(record, gold):
    return record.get("category") == gold["gold_category"] and _loose_text_match(record.get("brand"), gold["gold_brand"])


def _build_chaos_extraction_items():
    rng = random.Random(CHAOS_SEED)
    items = [dict(it) for it in build_extraction_set(SEED)]
    gold_by_id = {it["snippet_id"]: it["gold"] for it in items}
    n_corrupt = max(1, round(len(items) * HTML_CORRUPT_FRACTION))
    corrupt_ids = set(rng.sample([it["snippet_id"] for it in items], n_corrupt))
    stripped = []
    for it in items:
        html = _corrupt_html(it["html"], rng) if it["snippet_id"] in corrupt_ids else it["html"]
        stripped.append({"snippet_id": it["snippet_id"], "html": html})
    return stripped, gold_by_id, corrupt_ids


@guarded
def main():
    client = require_client()

    extraction_items, ext_gold, corrupt_ids = _build_chaos_extraction_items()
    classification_items = _load_stripped("classification.json")
    dedup_items = _load_stripped("dedup.json")
    cls_gold = {it["record_id"]: it for it in build_classification_set(SEED)}
    ddp_gold = {it["item_id"]: it["gold_cluster_id"] for it in build_dedup_set(SEED)}

    junky = _JunkyClient(client, JUNK_CALL_RATE, CHAOS_SEED)

    result = run_pipeline(extraction_items, classification_items, dedup_items, junky)

    if not isinstance(result, dict):
        not_passed(f"run_pipeline() must return a dict, got {type(result).__name__}")
    for key in ("extraction", "classification", "dedup", "catalog", "quarantine"):
        if key not in result:
            not_passed(f"run_pipeline() result missing key {key!r} under chaos input")

    ext_ids = [r.get("snippet_id") for r in result["extraction"]]
    if ext_ids != [it["snippet_id"] for it in extraction_items]:
        not_passed("run_pipeline()['extraction'] didn't cover every input item, in order, under chaos input")
    cls_ids = [r.get("record_id") for r in result["classification"]]
    if cls_ids != [it["record_id"] for it in classification_items]:
        not_passed("run_pipeline()['classification'] didn't cover every input item, in order, under chaos input")
    ddp_ids = [r.get("item_id") for r in result["dedup"]]
    if ddp_ids != [it["item_id"] for it in dedup_items]:
        not_passed("run_pipeline()['dedup'] didn't cover every input item, in order, under chaos input")

    quarantine_ids = {(q.get("stage"), q.get("id")) for q in result["quarantine"]}
    catalog_ids = {(c.get("stage"), c.get("id")) for c in result["catalog"]}

    should_quarantine = set()
    is_correct_by_id = {}
    for r in result["extraction"]:
        sid = r["snippet_id"]
        correct = _extraction_correct(r, ext_gold[sid])
        is_correct_by_id[("extraction", sid)] = correct
        if not correct:
            should_quarantine.add(("extraction", sid))
    for r in result["classification"]:
        rid = r["record_id"]
        correct = _classification_correct(r, cls_gold[rid])
        is_correct_by_id[("classification", rid)] = correct
        if not correct:
            should_quarantine.add(("classification", rid))

    graded_ids = set(is_correct_by_id.keys())
    catalog_graded = catalog_ids & graded_ids
    quarantine_graded = quarantine_ids & graded_ids

    catalog_correct = sum(1 for k in catalog_graded if is_correct_by_id[k])
    catalog_precision = catalog_correct / len(catalog_graded) if catalog_graded else 0.0

    _, quarantine_recall, _ = prf_from_sets(quarantine_graded, should_quarantine)

    failures = []
    if catalog_precision < CP2_MIN_CATALOG_PRECISION:
        failures.append(
            f"catalog precision under chaos={catalog_precision:.2f} < {CP2_MIN_CATALOG_PRECISION} "
            "-- too many objectively-wrong records reached the clean catalog"
        )
    if quarantine_recall < CP2_MIN_QUARANTINE_RECALL:
        failures.append(
            f"quarantine recall under chaos={quarantine_recall:.2f} < {CP2_MIN_QUARANTINE_RECALL} "
            "-- the gate is catching too few of the objectively-wrong records"
        )
    if not result["quarantine"]:
        failures.append("quarantine is empty under chaos input -- the quality gate never engaged")
    if not result["catalog"]:
        failures.append("catalog is empty under chaos input -- everything was quarantined, not graceful degradation")

    if failures:
        not_passed(
            "; ".join(failures)
            + f" (corrupted {len(corrupt_ids)}/{len(extraction_items)} html snippets, "
            f"{junky.junk_count}/{junky.call_count} generate/chat calls returned junk)"
        )

    passed(
        f"catalog_precision={catalog_precision:.2f}, quarantine_recall={quarantine_recall:.2f}, "
        f"catalog_size={len(result['catalog'])}, quarantine_size={len(result['quarantine'])}, "
        f"corrupted_html={len(corrupt_ids)}/{len(extraction_items)}, "
        f"junked_calls={junky.junk_count}/{junky.call_count}"
    )


if __name__ == "__main__":
    main()
