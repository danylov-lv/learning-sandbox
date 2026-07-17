"""Validator for 13-scraping-at-scale task 03 --
change-detection-and-fingerprinting.

Independent from the learner's own reasoning: the "did this product's
observable data actually change?" oracle is computed straight from this
module's generation inputs (`data/catalog.json` baseline values,
`data/target-spec.json`'s per-day cumulative price/in_stock overlay, and
`data/ground-truth.json`'s bad-record defect assignment), never from
anything the learner's code reports.

Why not just use `ground-truth.json`'s `change_days` id lists directly:
`change_days["D"]` records which ids got a delta APPLIED on day D, but a
tiny minority of those deltas are not actually OBSERVABLE on the rendered
page -- e.g. a `missing_price`/`price_na` bad-record defect masks the price
field to a constant regardless of the underlying value, and occasionally a
price's `round(old * uniform(0.85, 1.20), 2)` lands back on the same 2dp
value it started from. Treating those ids as "must be flagged changed"
would be asserting something that isn't actually true of the target's
responses, and a correct learner implementation would rightly not flag
them. `_observable_state()` below replays the exact same cumulative-overlay
and defect-masking logic `docker/target/app.py` applies, so "truly changed"
here means "the bytes a client can actually observe differ" -- the only
thing a fingerprint-based detector could ever be expected to catch.

Three checks, all against a SAMPLE of product ids (not the full 4,000 -- see
module 13's rate-limit budget):

  1. Primary: ~120 ids truly observably changed between day 0 and day 1,
     plus ~120 ids truly observably unchanged. Reset a fresh client, call
     `changed_between(0, 1, client_id, product_ids=sample)`, assert the
     returned set is EXACTLY the changed subset -- no false positives (an
     unchanged id flagged -> nonce leaking into the hash) and no false
     negatives (a changed id missed). Also asserts the client never got
     banned.

  2. Negative control: fetch the SAME day (day 0) for a handful of ids
     spanning all 4 markup versions (id % 4 == 0..3) TWICE, via the
     learner's own `build_fingerprint_index`, each call a fully independent
     fetch (so each carries its own fresh nonce). Assert the two
     fingerprint dicts agree exactly. This does not depend on any id being
     "changed" or "unchanged" across days at all -- it isolates the nonce
     variable alone, independent of check 1's pass/fail.

  3. Secondary sample: day 1 -> day 2 on a smaller, disjoint sample, same
     exact-match assertion as check 1 -- one more data point that the
     mechanism generalizes past a single day pair.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
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
from src.detect import build_fingerprint_index, changed_between  # noqa: E402

PRIMARY_CHANGED_N = 120
PRIMARY_UNCHANGED_N = 120
SECONDARY_CHANGED_N = 30
SECONDARY_UNCHANGED_N = 30
NEGCTRL_PER_VERSION = 2  # ids per markup version (id % 4 == 0..3) -> 8 total


def _cumulative_overlay(spec):
    """Reproduce docker/target/app.py's _CUMULATIVE_OVERLAY exactly: day D's
    effective delta per product is the merge of every day 1..D's raw delta,
    not just day D's own (a product's price/in_stock can be set by an
    earlier day and never touched again)."""
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
    """(price_as_observable, in_stock) for `pid` at `day` -- what a client
    can actually see, after the cumulative price/in_stock overlay AND the
    bad-record defect mask (missing_price / price_na both collapse price to
    a constant regardless of the underlying value; no defect touches
    in_stock, matching _apply_defect in docker/target/app.py)."""
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


def _negctrl_ids(n_products, per_version):
    """`per_version` ids for each of the 4 markup versions (version =
    1 + (id % 4)) -- the negative control only needs "same day fetched
    twice," it does not need to be a changed/unchanged id at all."""
    buckets = {0: [], 1: [], 2: [], 3: []}
    pid = 1
    while pid <= n_products and any(len(v) < per_version for v in buckets.values()):
        r = pid % 4
        if len(buckets[r]) < per_version:
            buckets[r].append(pid)
        pid += 1
    out = []
    for r, ids in buckets.items():
        if len(ids) < per_version:
            not_passed(f"could not find {per_version} ids with id%4=={r} for the negative control")
        out.extend(ids)
    return out


def _check_exact(ctx, got, expected):
    got = set(got) if not isinstance(got, set) else got
    expected = set(expected)
    missing = expected - got  # changed ids that were NOT flagged (false negatives)
    extra = got - expected  # unchanged ids WRONGLY flagged (false positives)
    if missing or extra:
        not_passed(
            f"{ctx}: changed_between mismatch -- "
            f"missing (changed but not flagged) = {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''} "
            f"({len(missing)} total), "
            f"extra (flagged but actually unchanged -- nonce leaking into the hash?) = "
            f"{sorted(extra)[:10]}{'...' if len(extra) > 10 else ''} ({len(extra)} total)"
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

    all_ids = list(range(1, n_products + 1))
    changed_01, unchanged_01 = _split_changed_unchanged(all_ids, 0, 1, catalog_by_id, overlay, bad_map)
    changed_12, unchanged_12 = _split_changed_unchanged(all_ids, 1, 2, catalog_by_id, overlay, bad_map)

    if len(changed_01) < PRIMARY_CHANGED_N or len(unchanged_01) < PRIMARY_UNCHANGED_N:
        not_passed("not enough truly-changed/unchanged day0->day1 ids to build the primary sample")
    if len(changed_12) < SECONDARY_CHANGED_N or len(unchanged_12) < SECONDARY_UNCHANGED_N:
        not_passed("not enough truly-changed/unchanged day1->day2 ids to build the secondary sample")

    client_id = "validate-03-change-detection"
    reset_client(client_id)

    # --- Check 1: primary sample, day 0 -> day 1 -------------------------
    primary_changed = changed_01[:PRIMARY_CHANGED_N]
    primary_unchanged = unchanged_01[:PRIMARY_UNCHANGED_N]
    primary_sample = primary_changed + primary_unchanged

    result1 = changed_between(0, 1, client_id, product_ids=primary_sample)
    if not isinstance(result1, set):
        not_passed(f"changed_between must return a set, got {type(result1).__name__}")
    _check_exact("day 0 -> day 1 (primary sample)", result1, primary_changed)

    state = get_client_state(client_id)
    if state.get("banned"):
        not_passed(
            f"client got banned during the primary sample run "
            f"(rate_limit_violations={state.get('rate_limit_violations')}, "
            f"honeypot_hits={state.get('honeypot_hits')}) -- pace requests, avoid honeypot ids"
        )

    # --- Check 2: negative control -- same day fetched twice, independent
    # requests, must produce IDENTICAL fingerprints despite differing
    # nonces, across all 4 markup versions.
    negctrl_ids = _negctrl_ids(n_products, NEGCTRL_PER_VERSION)
    idx_a = build_fingerprint_index(0, client_id, product_ids=negctrl_ids)
    idx_b = build_fingerprint_index(0, client_id, product_ids=negctrl_ids)
    if not isinstance(idx_a, dict) or not isinstance(idx_b, dict):
        not_passed("build_fingerprint_index must return a dict[int, str]")
    for pid in negctrl_ids:
        fp_a = idx_a.get(pid)
        fp_b = idx_b.get(pid)
        if fp_a is None or fp_b is None:
            not_passed(f"negative control: product {pid} (v={1 + pid % 4}) missing from a fingerprint index")
        if fp_a != fp_b:
            not_passed(
                f"negative control: product {pid} (markup v={1 + pid % 4}) fingerprint changed across two "
                f"independent fetches of the SAME day-0 page ({fp_a!r} != {fp_b!r}) -- "
                f"the volatile nonce is leaking into the hash"
            )

    state = get_client_state(client_id)
    if state.get("banned"):
        not_passed("client got banned during the negative-control run")

    # --- Check 3: secondary sample, day 1 -> day 2, disjoint ids ----------
    secondary_changed = changed_12[:SECONDARY_CHANGED_N]
    secondary_unchanged = unchanged_12[:SECONDARY_UNCHANGED_N]
    secondary_sample = secondary_changed + secondary_unchanged

    result3 = changed_between(1, 2, client_id, product_ids=secondary_sample)
    if not isinstance(result3, set):
        not_passed(f"changed_between must return a set, got {type(result3).__name__}")
    _check_exact("day 1 -> day 2 (secondary sample)", result3, secondary_changed)

    state = get_client_state(client_id)
    if state.get("banned"):
        not_passed("client got banned during the secondary sample run")

    passed(
        f"primary day0->day1 exact match ({len(primary_changed)} changed / {len(primary_unchanged)} unchanged, "
        f"sample={len(primary_sample)}); negative control stable across {len(negctrl_ids)} ids spanning all 4 "
        f"markup versions; secondary day1->day2 exact match ({len(secondary_changed)} changed / "
        f"{len(secondary_unchanged)} unchanged); client never banned "
        f"(requests={state.get('requests')}, rate_limit_violations={state.get('rate_limit_violations')})"
    )


if __name__ == "__main__":
    main()
