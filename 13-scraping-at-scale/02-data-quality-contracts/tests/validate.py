"""Validator for 13-scraping-at-scale task 02 (data-quality-contracts).

Run from the module root:

    uv run python 02-data-quality-contracts/tests/validate.py

This validator, not the learner, fetches the canonical record set (day 0,
every product id, GET /api/product/{id}) from the live target -- that keeps
grading deterministic and means this task grades the CONTRACT + gate logic
in src/contracts.py and src/gate.py, not a fetch layer. The fetch is paced
well under the target's token-bucket refill rate (see .authoring/design.md)
so it never trips the rate limiter or gets banned; it takes roughly a
minute and a half for the full ~4000-product catalog. Bad-record ids by
defect type come from `harness.common.load_ground_truth()`'s
`bad_records.by_defect` -- never from the learner's own output.

Checks:
  1. run_gate(records, workdir) on the full fetched set: quarantine ids ==
     EXACTLY the union of ground truth's bad_records.by_defect (set
     equality, not a superset/subset check); clean ids == EXACTLY the
     complement. Both sinks must actually contain the number of lines their
     own summary dict claims.
  2. Every clean row is independently re-checked (by this validator's own
     defect detector, computed straight from the JSON, not by calling the
     learner's schema) against the same rules the contract is supposed to
     enforce -- a clean row with a detectable defect is a bug even if the
     id-set check above somehow passed.
  3. Every quarantined row carries a non-empty `reason` that mentions the
     field its TRUE defect type actually touches (a bad_currency id's
     reason must mention currency, a price-family defect's reason must
     mention price, etc.) -- wording is free, the field is not.
  4. field_completeness(records) matches an independently recomputed
     completeness report (tolerance 0.01) over every field that appears in
     the corpus.
  5. completeness_alert fires on a synthetic batch with price completeness
     deliberately dropped to 0.5 against a 0.9 threshold, does NOT fire on
     a fully-complete synthetic batch, and alerts (observed=0.0) for a
     threshold field that never appears in the batch at all.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    TargetClient,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)

from src.contracts import ALLOWED_CURRENCIES  # noqa: E402
from src.gate import completeness_alert, field_completeness, run_gate  # noqa: E402

# Requests/sec target for the validator's own fetch of the canonical corpus.
# The target's token bucket refills at 50/sec with a burst capacity of 25;
# this is a plain sequential loop (one in-flight request at a time, no
# burst possible), paced with a safety margin under the refill rate.
FETCH_RATE = 40.0
MAX_RETRIES_PER_ID = 5

# Maps a ground-truth defect type to the record field its quarantine
# `reason` must mention -- computed here, independently of any pandera
# check name the learner's own schema happens to use.
DEFECT_FIELD = {
    "missing_price": "price",
    "price_na": "price",
    "negative_price": "price",
    "bad_currency": "currency",
    "empty_title": "title",
    "truncated": "description",
}


def _fetch_all_records(n_products, day=0):
    client = TargetClient()
    records = {}
    min_interval = 1.0 / FETCH_RATE
    try:
        for pid in range(1, n_products + 1):
            t0 = time.perf_counter()
            attempts = 0
            while True:
                resp = client.get(f"/api/product/{pid}", params={"day": day})
                if resp.status_code == 200:
                    records[pid] = resp.json()
                    break
                if resp.status_code == 429 and attempts < MAX_RETRIES_PER_ID:
                    attempts += 1
                    time.sleep(float(resp.headers.get("Retry-After", "1")))
                    continue
                not_passed(
                    f"unexpected status {resp.status_code} fetching GET /api/product/{pid} "
                    "-- is the target stack up and healthy? (docker compose ps)"
                )
            elapsed = time.perf_counter() - t0
            remaining = min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
    finally:
        client.close()
    return records


def _is_complete(value):
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _independent_completeness(records):
    fields = set()
    for r in records:
        fields.update(r.keys())
    total = len(records)
    result = {}
    for field in fields:
        count = sum(1 for r in records if field in r and _is_complete(r[field]))
        result[field] = count / total if total else 0.0
    return result


def _own_defect_fields(rec):
    """Independent re-derivation of which fields make a record invalid,
    straight from the JSON -- deliberately not calling the learner's own
    pandera schema, so a buggy schema can't validate itself as correct."""
    bad = set()
    if "price" not in rec:
        bad.add("price")
    else:
        price = rec["price"]
        if isinstance(price, bool) or isinstance(price, str):
            bad.add("price")
        elif not isinstance(price, (int, float)) or price <= 0:
            bad.add("price")
    if rec.get("currency") not in ALLOWED_CURRENCIES:
        bad.add("currency")
    title = rec.get("title")
    if not isinstance(title, str) or title.strip() == "":
        bad.add("title")
    return bad


def _read_jsonl(path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _synthetic_batch(price_present_fraction, n=10):
    n_present = round(n * price_present_fraction)
    batch = []
    for i in range(n):
        rec = {
            "id": 90_000 + i,
            "title": f"Synthetic Item {i}",
            "currency": "USD",
            "description": "A synthetic record used only to exercise the completeness monitor.",
        }
        if i < n_present:
            rec["price"] = 9.99 + i
        batch.append(rec)
    return batch


def _check_gate_split(records, all_ids, all_bad_ids, id_to_defect):
    workdir = Path(tempfile.mkdtemp(prefix="dq-gate-"))
    summary = run_gate(records, workdir)

    for key in ("clean_count", "quarantine_count", "clean_path", "quarantine_path"):
        if key not in summary:
            not_passed(f"run_gate's returned summary is missing key {key!r}: got {summary!r}")

    clean_rows = _read_jsonl(summary["clean_path"])
    quarantine_rows = _read_jsonl(summary["quarantine_path"])

    if summary["clean_count"] != len(clean_rows):
        not_passed(
            f"summary clean_count={summary['clean_count']} does not match "
            f"{len(clean_rows)} lines actually written to {summary['clean_path']}"
        )
    if summary["quarantine_count"] != len(quarantine_rows):
        not_passed(
            f"summary quarantine_count={summary['quarantine_count']} does not match "
            f"{len(quarantine_rows)} lines actually written to {summary['quarantine_path']}"
        )

    clean_ids = {r["id"] for r in clean_rows}
    quarantine_ids = {r["id"] for r in quarantine_rows}
    expected_clean_ids = all_ids - all_bad_ids

    if quarantine_ids != all_bad_ids:
        missing = sorted(all_bad_ids - quarantine_ids)
        extra = sorted(quarantine_ids - all_bad_ids)
        not_passed(
            f"quarantine ids do not exactly match ground-truth bad ids: "
            f"{len(missing)} missing (e.g. {missing[:5]}), {len(extra)} extra (e.g. {extra[:5]})"
        )
    if clean_ids != expected_clean_ids:
        missing = sorted(expected_clean_ids - clean_ids)
        extra = sorted(clean_ids - expected_clean_ids)
        not_passed(
            f"clean ids do not exactly match the complement of bad ids: "
            f"{len(missing)} missing (e.g. {missing[:5]}), {len(extra)} extra (e.g. {extra[:5]})"
        )

    for row in clean_rows:
        defects = _own_defect_fields(row)
        if defects:
            not_passed(
                f"clean row id={row.get('id')} still has a detectable defect in "
                f"field(s) {sorted(defects)} -- it should have been quarantined"
            )

    for row in quarantine_rows:
        rid = row.get("id")
        reason = row.get("reason")
        if not reason or not str(reason).strip():
            not_passed(f"quarantine row id={rid} has no non-empty 'reason'")
        expected_field = DEFECT_FIELD.get(id_to_defect.get(rid))
        if expected_field and expected_field not in str(reason).lower():
            not_passed(
                f"quarantine reason for id={rid} (true defect={id_to_defect.get(rid)!r}) "
                f"does not mention {expected_field!r}: got reason={reason!r}"
            )

    return len(all_bad_ids), len(expected_clean_ids)


def _check_field_completeness(records):
    completeness = field_completeness(records)
    if not isinstance(completeness, dict):
        not_passed(f"field_completeness must return a dict, got {type(completeness).__name__}")

    expected = _independent_completeness(records)
    for field, exp_val in expected.items():
        got = completeness.get(field)
        if got is None:
            not_passed(f"field_completeness result is missing field {field!r}")
        if abs(got - exp_val) > 0.01:
            not_passed(
                f"field_completeness[{field!r}]={got} does not match independent "
                f"recompute {exp_val} (tol 0.01)"
            )


def _check_completeness_alert():
    degraded = _synthetic_batch(price_present_fraction=0.5)
    degraded_completeness = field_completeness(degraded)
    price_rate = degraded_completeness.get("price")
    if price_rate is None or abs(price_rate - 0.5) > 0.05:
        not_passed(
            f"field_completeness on a synthetic batch with 5/10 price keys present "
            f"returned {price_rate!r}, expected ~0.5"
        )

    thresholds = {"price": 0.9, "title": 0.9}
    alerts = completeness_alert(degraded_completeness, thresholds)
    by_field = {a.get("field"): a for a in alerts}
    if "price" not in by_field:
        not_passed(
            f"completeness_alert did not fire for 'price' at observed~{price_rate} "
            f"vs threshold 0.9: alerts={alerts}"
        )
    price_alert = by_field["price"]
    if abs(price_alert.get("observed", -1) - price_rate) > 0.01:
        not_passed(
            f"completeness_alert price alert observed={price_alert.get('observed')} "
            f"does not match field_completeness result {price_rate}"
        )
    if abs(price_alert.get("threshold", -1) - 0.9) > 1e-9:
        not_passed(
            f"completeness_alert price alert threshold={price_alert.get('threshold')} "
            "does not match the 0.9 threshold passed in"
        )
    if "title" in by_field:
        not_passed(
            f"completeness_alert fired for 'title' (fully complete in the synthetic batch) "
            f"which should not be below its 0.9 threshold: {by_field['title']}"
        )

    complete = _synthetic_batch(price_present_fraction=1.0)
    complete_completeness = field_completeness(complete)
    no_alerts = completeness_alert(complete_completeness, thresholds)
    if no_alerts:
        not_passed(f"completeness_alert fired on a fully-complete synthetic batch: {no_alerts}")

    unseen_alerts = completeness_alert(complete_completeness, {"totally_absent_field": 0.5})
    unseen_by_field = {a.get("field"): a for a in unseen_alerts}
    if "totally_absent_field" not in unseen_by_field:
        not_passed(
            "completeness_alert did not alert for a threshold field that never appears "
            f"in the completeness report at all: alerts={unseen_alerts}"
        )
    if abs(unseen_by_field["totally_absent_field"].get("observed", -1) - 0.0) > 1e-9:
        not_passed(
            "completeness_alert for a never-observed field should report observed=0.0, got "
            f"{unseen_by_field['totally_absent_field']}"
        )


@guarded
def main():
    gt = load_ground_truth()
    n_products = gt["n_products"]
    bad_by_defect = gt["bad_records"]["by_defect"]

    all_bad_ids = set()
    id_to_defect = {}
    for defect, ids in bad_by_defect.items():
        for i in ids:
            all_bad_ids.add(i)
            id_to_defect[i] = defect

    print(
        f"fetching {n_products} canonical records from the target "
        f"(day=0, paced ~{FETCH_RATE:.0f} req/s -- this takes a while)...",
        file=sys.stderr,
    )
    records_by_id = _fetch_all_records(n_products)
    all_ids = set(records_by_id.keys())
    if all_ids != set(range(1, n_products + 1)):
        not_passed(f"fetched {len(all_ids)} records, expected exactly {n_products} (ids 1..{n_products})")

    records = [records_by_id[i] for i in sorted(records_by_id)]

    n_bad, n_clean = _check_gate_split(records, all_ids, all_bad_ids, id_to_defect)
    _check_field_completeness(records)
    _check_completeness_alert()

    passed(
        f"quarantine == exactly {n_bad} bad ids across {len(bad_by_defect)} defect types, "
        f"clean == exactly {n_clean} good ids, all reasons field-consistent, "
        "completeness monitor verified against independent recompute + synthetic degradation"
    )


if __name__ == "__main__":
    main()
