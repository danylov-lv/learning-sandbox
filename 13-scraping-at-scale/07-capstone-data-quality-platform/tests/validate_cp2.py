"""CP2 validator for the s13 capstone -- CHAOS + CHANGE DETECTION.

Independent of anything the learner's code reports. Three groups of checks:

  (a) Chaos resilience: `run_pipeline(..., chaos=True)` for day 0 AND day 1
      (two separate full-catalog runs, two separate client ids) -- under
      chaos the target cycles markup version by wall-clock instead of by
      product id, so a crawl that takes long enough to span a version
      boundary genuinely serves several different products under several
      different encodings within the SAME run. Extraction completeness
      (scored against the catalog oracle, day-0/day-1 overlay applied) must
      stay above a robust threshold despite that -- and the client must
      never get banned.

  (b) Change detection exact match (task 03's concept): a sample mixing
      ~120 ids truly observably changed between day 0 and day 1 with ~120
      ids truly observably unchanged (oracle computed straight from
      `data/catalog.json` + `data/target-spec.json`'s cumulative overlay +
      bad-record defect masking, replaying `docker/target/app.py`'s own
      logic -- see `_observable_state` below), calling the learner's
      `changed_between(0, 1, ..., product_ids=sample)`. A negative control
      (a known-unchanged id) must not be flagged.

  (c) Idempotent recovery: `build_fingerprint_index` and `changed_between`
      are each called TWICE in a row with identical arguments (simulating
      an interrupted-then-resumed run) -- both calls must produce IDENTICAL
      results, both must independently match the oracle exactly. No drift,
      no duplicates.

Correctness is by ground-truth/oracle comparison only -- never a wall-clock
deadline (a correct-but-slower machine must never fail this checkpoint on
time alone).

Run from the MODULE ROOT:

    uv run python 07-capstone-data-quality-platform/tests/validate_cp2.py
"""

import json
import sys
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    get_client_state,
    guarded,
    load_catalog,
    load_ground_truth,
    load_target_spec,
    not_passed,
    passed,
    reset_client,
)
from src.changedetect import build_fingerprint_index, changed_between  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402

PRICE_TOLERANCE = 0.01
DESC_PREFIX_MIN_RATIO = 0.6
MAX_RATE_LIMIT_VIOLATIONS = 20

CHAOS_COMPLETENESS_MIN = 0.95
CHAOS_FIELD_SAMPLE_PER_RESIDUE = 15

PRIMARY_CHANGED_N = 120
PRIMARY_UNCHANGED_N = 120

FIELDS = ("title", "price", "currency", "in_stock", "seller_name", "review_count", "description")


# --------------------------------------------------------------------------
# Independent oracle -- reproduces docker/target/app.py's cumulative overlay
# and bad-record defect masking exactly, same technique task 03's own
# validator uses. Deliberately does not import anything from task 03 (each
# task's validator is self-contained) or from src/ (this must not depend on
# the learner's own reasoning).
# --------------------------------------------------------------------------

def _cumulative_overlay(spec):
    raw = {
        int(d): {int(pid): delta for pid, delta in changes.items()}
        for d, changes in spec["change_days"]["days"].items()
    }
    n_days = spec["change_days"]["n_days"]
    overlay = {0: {}}
    running = {}
    for d in range(1, n_days):
        running = {**running, **raw.get(d, {})}
        overlay[d] = dict(running)
    return overlay


def _observable_state(pid, day, catalog_by_id, overlay, bad_map):
    base = catalog_by_id[pid]
    price = base["price"]
    in_stock = base["in_stock"]
    delta = overlay.get(day, {}).get(pid)
    if delta:
        if "price" in delta:
            price = delta["price"]
        if "in_stock" in delta:
            in_stock = delta["in_stock"]
    defect = bad_map.get(pid)
    if defect == "missing_price":
        price_obs = None
    elif defect == "price_na":
        price_obs = "N/A"
    else:
        price_obs = price
    return (price_obs, in_stock)


def _split_changed_unchanged(pids, day_prev, day_curr, catalog_by_id, overlay, bad_map):
    changed, unchanged = [], []
    for pid in pids:
        a = _observable_state(pid, day_prev, catalog_by_id, overlay, bad_map)
        b = _observable_state(pid, day_curr, catalog_by_id, overlay, bad_map)
        (changed if a != b else unchanged).append(pid)
    return changed, unchanged


def _effective_value(pid, day, catalog_by_id, overlay):
    base = catalog_by_id[pid]
    delta = overlay.get(day, {}).get(pid, {})
    price = delta.get("price", base["price"])
    in_stock = delta.get("in_stock", base["in_stock"])
    return price, in_stock


def _normalize_ws(s):
    return " ".join((s or "").split())


def _description_ok(extracted, expected):
    e = _normalize_ws(extracted)
    x = _normalize_ws(expected)
    if not e or not x:
        return False
    if e == x:
        return True
    return x.startswith(e) and len(e) >= DESC_PREFIX_MIN_RATIO * len(x)


def _read_jsonl(path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _score_extraction(result, catalog_by_id, day, overlay, bad_map):
    """Overall field-correctness score (correct / total field checks) over
    a sample of CLEAN ids (bad-record ids excluded -- their true fields are
    deliberately defective, comparing them to the catalog would be the
    wrong oracle), spread across all 4 id%4 markup-version residues."""
    clean_rows = _read_jsonl(result["clean_path"])
    quarantine_rows = _read_jsonl(result["quarantine_path"])
    rows_by_id = {r["id"]: r for r in clean_rows + quarantine_rows}

    clean_ids = [pid for pid in catalog_by_id if bad_map.get(pid) is None]
    by_residue = {0: [], 1: [], 2: [], 3: []}
    for pid in clean_ids:
        by_residue[pid % 4].append(pid)
    sample = []
    for r in (0, 1, 2, 3):
        group = by_residue[r]
        step = max(1, len(group) // CHAOS_FIELD_SAMPLE_PER_RESIDUE)
        sample.extend(group[::step][:CHAOS_FIELD_SAMPLE_PER_RESIDUE])

    correct = 0
    total = 0
    for pid in sample:
        base = catalog_by_id[pid]
        expected_price, expected_in_stock = _effective_value(pid, day, catalog_by_id, overlay)
        rec = rows_by_id.get(pid)
        if rec is None:
            total += len(FIELDS)
            continue
        price = rec.get("price")
        try:
            price_ok = price is not None and abs(float(price) - float(expected_price)) < PRICE_TOLERANCE
        except (TypeError, ValueError):
            price_ok = False
        rc = rec.get("review_count")
        try:
            rc_ok = rc is not None and not isinstance(rc, bool) and int(rc) == int(base["review_count"])
        except (TypeError, ValueError):
            rc_ok = False
        checks = {
            "title": rec.get("title") == base["title"],
            "price": price_ok,
            "currency": rec.get("currency") == base["currency"],
            "in_stock": isinstance(rec.get("in_stock"), bool) and rec["in_stock"] == expected_in_stock,
            "seller_name": rec.get("seller_name") == base["seller_name"],
            "review_count": rc_ok,
            "description": _description_ok(rec.get("description"), base["description"]),
        }
        for ok in checks.values():
            total += 1
            if ok:
                correct += 1

    return (correct / total) if total else 0.0, len(sample)


def _check_exact(ctx, got, expected):
    got = set(got) if not isinstance(got, set) else got
    expected = set(expected)
    missing = expected - got
    extra = got - expected
    if missing or extra:
        not_passed(
            f"{ctx}: changed_between mismatch -- "
            f"missing (changed but not flagged) = {sorted(missing)[:10]} ({len(missing)} total), "
            f"extra (flagged but actually unchanged -- nonce leaking into the fingerprint?) = "
            f"{sorted(extra)[:10]} ({len(extra)} total)"
        )


@guarded
def main():
    gt = load_ground_truth()
    catalog = load_catalog()
    spec = load_target_spec()
    n_products = gt["n_products"]

    catalog_by_id = {p["id"]: p for p in catalog["products"]}
    overlay = _cumulative_overlay(spec)
    bad_map = {int(pid): defect for pid, defect in spec["bad_records"]["by_id"].items()}

    # --- (a) chaos resilience: full pipeline runs for day 0 and day 1 ---
    client_day0 = f"cp2-chaos-day0-{uuid.uuid4()}"
    reset_client(client_day0)
    result0 = run_pipeline(client_day0, day=0, chaos=True, workdir=TASK_ROOT / "run" / "cp2-day0")
    if not isinstance(result0, dict) or "clean_path" not in result0:
        not_passed(f"run_pipeline(day=0, chaos=True) did not return the expected dict: {result0!r}")
    state0 = get_client_state(client_day0)
    if state0.get("banned"):
        not_passed(f"chaos day-0 client got BANNED -- state: {state0}")
    if state0.get("honeypot_hits", 0) != 0:
        not_passed(f"chaos day-0 client hit {state0['honeypot_hits']} honeypot(s)")
    if state0.get("rate_limit_violations", 0) > MAX_RATE_LIMIT_VIOLATIONS:
        not_passed(f"chaos day-0 client racked up {state0['rate_limit_violations']} rate-limit violations")
    score0, n0 = _score_extraction(result0, catalog_by_id, 0, overlay, bad_map)
    if score0 < CHAOS_COMPLETENESS_MIN:
        not_passed(
            f"day-0 chaos-mode extraction score {score0:.3f} over {n0} sampled clean products "
            f"< robust floor {CHAOS_COMPLETENESS_MIN} -- markup chaos broke the fallback chain"
        )

    client_day1 = f"cp2-chaos-day1-{uuid.uuid4()}"
    reset_client(client_day1)
    result1 = run_pipeline(client_day1, day=1, chaos=True, workdir=TASK_ROOT / "run" / "cp2-day1")
    if not isinstance(result1, dict) or "clean_path" not in result1:
        not_passed(f"run_pipeline(day=1, chaos=True) did not return the expected dict: {result1!r}")
    state1 = get_client_state(client_day1)
    if state1.get("banned"):
        not_passed(f"chaos day-1 client got BANNED -- state: {state1}")
    if state1.get("honeypot_hits", 0) != 0:
        not_passed(f"chaos day-1 client hit {state1['honeypot_hits']} honeypot(s)")
    if state1.get("rate_limit_violations", 0) > MAX_RATE_LIMIT_VIOLATIONS:
        not_passed(f"chaos day-1 client racked up {state1['rate_limit_violations']} rate-limit violations")
    score1, n1 = _score_extraction(result1, catalog_by_id, 1, overlay, bad_map)
    if score1 < CHAOS_COMPLETENESS_MIN:
        not_passed(
            f"day-1 chaos-mode extraction score {score1:.3f} over {n1} sampled clean products "
            f"< robust floor {CHAOS_COMPLETENESS_MIN} -- markup chaos broke the fallback chain"
        )

    # --- (b) change detection exact match + negative control ---
    all_ids = list(range(1, n_products + 1))
    changed_01, unchanged_01 = _split_changed_unchanged(all_ids, 0, 1, catalog_by_id, overlay, bad_map)
    if len(changed_01) < PRIMARY_CHANGED_N or len(unchanged_01) < PRIMARY_UNCHANGED_N:
        not_passed("not enough truly-changed/unchanged day0->day1 ids to build the sample -- ground truth mismatch?")

    primary_changed = changed_01[:PRIMARY_CHANGED_N]
    primary_unchanged = unchanged_01[:PRIMARY_UNCHANGED_N]
    sample = primary_changed + primary_unchanged

    cd_client = f"cp2-changedetect-{uuid.uuid4()}"
    reset_client(cd_client)

    result_a = changed_between(0, 1, cd_client, product_ids=sample)
    if not isinstance(result_a, set):
        not_passed(f"changed_between must return a set, got {type(result_a).__name__}")
    _check_exact("day 0 -> day 1 (first call)", result_a, primary_changed)

    state_cd = get_client_state(cd_client)
    if state_cd.get("banned"):
        not_passed(f"change-detection client got banned -- state: {state_cd}")

    known_unchanged = primary_unchanged[0]
    if known_unchanged in result_a:
        not_passed(f"negative control failed: known-unchanged product {known_unchanged} was flagged as changed")

    # --- (c) idempotent recovery: repeat both calls, require convergence ---
    idx_a = build_fingerprint_index(0, cd_client, product_ids=sample)
    idx_b = build_fingerprint_index(0, cd_client, product_ids=sample)
    if not isinstance(idx_a, dict) or not isinstance(idx_b, dict):
        not_passed("build_fingerprint_index must return a dict[int, str]")
    if set(idx_a.keys()) != set(sample) or set(idx_b.keys()) != set(sample):
        not_passed(
            f"build_fingerprint_index did not return exactly the {len(sample)} requested ids "
            f"(first call: {len(idx_a)} keys, second call: {len(idx_b)} keys) -- possible duplicates/omissions"
        )
    if idx_a != idx_b:
        diff = {pid for pid in sample if idx_a.get(pid) != idx_b.get(pid)}
        not_passed(f"build_fingerprint_index diverged across two independent calls for {len(diff)} id(s), e.g. {sorted(diff)[:5]}")

    result_b = changed_between(0, 1, cd_client, product_ids=sample)
    if not isinstance(result_b, set):
        not_passed(f"changed_between must return a set, got {type(result_b).__name__} on the second call")
    if result_b != result_a:
        not_passed(
            f"changed_between did not converge across two identical calls -- first call flagged "
            f"{len(result_a)} ids, second flagged {len(result_b)}, diff={sorted(result_a ^ result_b)[:10]}"
        )
    _check_exact("day 0 -> day 1 (second/repeated call)", result_b, primary_changed)

    state_cd = get_client_state(cd_client)
    if state_cd.get("banned"):
        not_passed(f"change-detection client got banned during the repeat-call check -- state: {state_cd}")

    passed(
        f"chaos day0 extraction score={score0:.3f} (n={n0}), day1 score={score1:.3f} (n={n1}), both clients "
        f"unbanned; change_between exact match on {len(sample)}-id sample ({len(primary_changed)} changed / "
        f"{len(primary_unchanged)} unchanged), negative control held, idempotent across 2 repeated calls "
        f"(fingerprint index + changed set both identical both times)"
    )


if __name__ == "__main__":
    main()
