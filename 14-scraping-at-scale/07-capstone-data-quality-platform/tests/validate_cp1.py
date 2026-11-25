"""CP1 validator for the s13 capstone -- STEADY STATE (day 0, no chaos).

Runs the learner's `run_pipeline(client_id, day=0)` exactly once (the full
crawl is the expensive part, ~2-4 minutes at a polite pace against this
target's tuned rate limit + budget router) and checks every pillar this
checkpoint is about, never trusting the pipeline's own returned numbers as
truth -- every assertion below recomputes its oracle independently from
`data/catalog.json` / `data/ground-truth.json` and the target's own
`/__debug/client` state:

  (a) discovery: the pipeline's `ids` are EXACTLY the real product id set
      (task 01's concept) -- right count, no duplicates, no honeypot ids.
  (b) politeness: the client used for the run ended `banned=False`,
      `honeypot_hits=0`, `header_rejections=0`, and a small
      `rate_limit_violations` count.
  (c) data-quality gate (task 02's concept): the quarantine sink contains
      EXACTLY the union of ground truth's `bad_records.by_defect` (set
      equality), the clean sink contains EXACTLY the complement, every
      clean row independently re-checks as defect-free, and every
      quarantine row's `reason` mentions the field its true defect
      actually touches.
  (d) markup resilience (task 04's concept): a sample of clean ids spread
      across all 4 markup versions (`id % 4`) has every HTML-visible field
      matching the catalog oracle.
  (e) budget router (task 05's concept): completeness (review_count > 0
      products with rating/shipping_info populated) meets the
      `completeness_target`, and the derived modeled cost is well under
      `all_render_cost` and close to `mixed_cost`.
  (f) observability (task 06's concept): `src/metrics.py`'s registry, read
      directly via `prometheus_client.generate_latest` right after the run
      (no HTTP server needed for this checkpoint), exposes every required
      metric family and shows real movement.

Run from the MODULE ROOT:

    uv run python 07-capstone-data-quality-platform/tests/validate_cp1.py
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
    not_passed,
    passed,
    reset_client,
)
from src.pipeline import run_pipeline  # noqa: E402
from src import metrics  # noqa: E402

PRICE_TOLERANCE = 0.01
MAX_RATE_LIMIT_VIOLATIONS = 20  # a handful of 429s recovered via backoff is fine, a ban is not
FIELD_SAMPLE_PER_RESIDUE = 20  # -> up to 80 clean products spread across id%4 residues
DESC_PREFIX_MIN_RATIO = 0.6
WASTE_TOLERANCE_FRACTION = 0.08
COST_MARGIN = 1.15  # derived modeled cost may be at most 1.15x the reference mixed_cost

DEFECT_FIELD = {
    "missing_price": "price",
    "price_na": "price",
    "negative_price": "price",
    "bad_currency": "currency",
    "empty_title": "title",
    "truncated": "description",
}

REQUIRED_METRIC_FAMILIES = {
    "spider_pages_fetched",
    "spider_records_quarantined",
    "spider_fetch_errors",
    "spider_fetch_latency_seconds",
    "spider_field_completeness",
}
BAN_OR_HONEYPOT_FAMILIES = {"spider_banned", "spider_honeypot_hits"}


def _read_jsonl(path):
    text = Path(path).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


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


def _own_defect_fields(rec):
    """Independent re-derivation of which fields make a record invalid --
    deliberately not calling the learner's own quality_check, so a buggy
    gate can't validate itself as correct. Mirrors task 02's validator."""
    bad = set()
    price = rec.get("price")
    if price is None or isinstance(price, bool) or isinstance(price, str):
        bad.add("price")
    elif not isinstance(price, (int, float)) or price <= 0:
        bad.add("price")
    if rec.get("currency") not in ("USD", "EUR", "GBP", "CAD"):
        bad.add("currency")
    title = rec.get("title")
    if not isinstance(title, str) or title.strip() == "":
        bad.add("title")
    desc = rec.get("description") or ""
    if "[TRNC]" in desc:
        bad.add("description")
    return bad


def _sample_ids_by_residue(ids, per_residue):
    by_residue = {0: [], 1: [], 2: [], 3: []}
    for pid in sorted(ids):
        by_residue[pid % 4].append(pid)
    sample = []
    for r in (0, 1, 2, 3):
        group = by_residue[r]
        if not group:
            continue
        step = max(1, len(group) // per_residue)
        sample.extend(group[::step][:per_residue])
    return sample


def _check_result_shape(result):
    required_keys = (
        "ids", "clean_count", "quarantine_count", "clean_path", "quarantine_path",
        "summary_path", "n_rendered", "completeness", "modeled_cost",
    )
    for key in required_keys:
        if key not in result:
            not_passed(f"run_pipeline's returned dict is missing key {key!r}: got keys {sorted(result.keys())}")


def _check_discovery(result, gt):
    n_products = gt["n_products"]
    honeypot_ids = set(gt["honeypot_ids"])
    ids = result["ids"]
    if not isinstance(ids, list):
        not_passed(f"run_pipeline's 'ids' must be a list, got {type(ids).__name__}")
    id_set = set(ids)
    if len(ids) != len(id_set):
        not_passed(f"run_pipeline returned {len(ids) - len(id_set)} duplicate id(s) in 'ids'")
    honeypots_seen = id_set & honeypot_ids
    if honeypots_seen:
        not_passed(f"run_pipeline processed {len(honeypots_seen)} honeypot id(s), e.g. {sorted(honeypots_seen)[:5]}")
    expected_ids = set(range(1, n_products + 1))
    if id_set != expected_ids:
        missing = sorted(expected_ids - id_set)[:5]
        extra = sorted(id_set - expected_ids)[:5]
        not_passed(
            f"run_pipeline's id set does not match the real product range 1..{n_products}: "
            f"missing e.g. {missing}, extra e.g. {extra}"
        )
    return id_set


def _check_client_health(client_id):
    state = get_client_state(client_id)
    if state.get("banned"):
        not_passed(f"client got BANNED during run_pipeline -- state: {state}")
    if state.get("honeypot_hits", 0) != 0:
        not_passed(f"client hit {state['honeypot_hits']} honeypot(s) during run_pipeline -- state: {state}")
    if state.get("header_rejections", 0) != 0:
        not_passed(f"client got {state['header_rejections']} header rejection(s) -- state: {state}")
    violations = state.get("rate_limit_violations", 0)
    if violations > MAX_RATE_LIMIT_VIOLATIONS:
        not_passed(
            f"client racked up {violations} rate-limit violations, expected <= "
            f"{MAX_RATE_LIMIT_VIOLATIONS} -- pace the dispatch rate explicitly: {state}"
        )
    return violations


def _check_gate_split(result, all_bad_ids, id_to_defect):
    clean_rows = _read_jsonl(result["clean_path"])
    quarantine_rows = _read_jsonl(result["quarantine_path"])

    if result["clean_count"] != len(clean_rows):
        not_passed(f"summary clean_count={result['clean_count']} != {len(clean_rows)} lines in {result['clean_path']}")
    if result["quarantine_count"] != len(quarantine_rows):
        not_passed(f"summary quarantine_count={result['quarantine_count']} != {len(quarantine_rows)} lines in {result['quarantine_path']}")

    clean_ids = {r["id"] for r in clean_rows}
    quarantine_ids = {r["id"] for r in quarantine_rows}

    if quarantine_ids != all_bad_ids:
        missing = sorted(all_bad_ids - quarantine_ids)[:5]
        extra = sorted(quarantine_ids - all_bad_ids)[:5]
        not_passed(
            f"quarantine ids do not exactly match ground-truth bad ids: "
            f"{len(missing)} missing (e.g. {missing}), {len(extra)} extra (e.g. {extra})"
        )

    for row in clean_rows:
        defects = _own_defect_fields(row)
        if defects:
            not_passed(f"clean row id={row.get('id')} still has a detectable defect in field(s) {sorted(defects)}")

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

    return clean_rows, quarantine_rows


def _check_field_sample(clean_rows, products_by_id, bad_ids):
    rows_by_id = {r["id"]: r for r in clean_rows}
    sample = _sample_ids_by_residue([pid for pid in rows_by_id if pid not in bad_ids], FIELD_SAMPLE_PER_RESIDUE)
    checked = 0
    for pid in sample:
        rec = rows_by_id[pid]
        truth = products_by_id[pid]
        if rec.get("title") != truth["title"]:
            not_passed(f"product {pid}: title={rec.get('title')!r}, catalog expects {truth['title']!r}")
        price = rec.get("price")
        if price is None or abs(float(price) - float(truth["price"])) > PRICE_TOLERANCE:
            not_passed(f"product {pid}: price={price!r}, catalog expects ~{truth['price']}")
        if rec.get("currency") != truth["currency"]:
            not_passed(f"product {pid}: currency={rec.get('currency')!r}, catalog expects {truth['currency']!r}")
        if not isinstance(rec.get("in_stock"), bool) or rec["in_stock"] != truth["in_stock"]:
            not_passed(f"product {pid}: in_stock={rec.get('in_stock')!r}, catalog expects {truth['in_stock']!r}")
        if rec.get("seller_name") != truth["seller_name"]:
            not_passed(f"product {pid}: seller_name={rec.get('seller_name')!r}, catalog expects {truth['seller_name']!r}")
        rc = rec.get("review_count")
        if rc is None or int(rc) != int(truth["review_count"]):
            not_passed(f"product {pid}: review_count={rc!r}, catalog expects {truth['review_count']}")
        if not _description_ok(rec.get("description"), truth["description"]):
            not_passed(f"product {pid}: description does not match catalog (markup version id%4={pid % 4})")
        checked += 1
    if checked < len(sample) // 2 + 1 and checked < 10:
        not_passed(f"only {checked} sample products were checkable -- sampling logic may be broken")
    return checked


def _check_budget(clean_rows, quarantine_rows, products_by_id, id_set, cm):
    rows_by_id = {r["id"]: r for r in clean_rows + quarantine_rows}
    required_ids = {pid for pid in id_set if products_by_id[pid].get("review_count", 0) > 0}
    if not required_ids:
        not_passed("catalog has zero products with review_count > 0 -- data generation looks broken")

    def _is_rendered(rec):
        return rec.get("rating") is not None and rec.get("shipping_info") is not None

    rendered_ids = {pid for pid, rec in rows_by_id.items() if _is_rendered(rec)}
    matched_required = required_ids & rendered_ids
    completeness = len(matched_required) / len(required_ids)
    if completeness < cm["completeness_target"]:
        missing = sorted(required_ids - rendered_ids)[:5]
        not_passed(
            f"completeness {completeness:.4f} < target {cm['completeness_target']} "
            f"({len(matched_required)}/{len(required_ids)} required renders present, e.g. missing {missing})"
        )

    n_rendered = len(rendered_ids)
    total_cost = len(id_set) * 1.0 + n_rendered * 7.0
    if total_cost >= cm["all_render_cost"]:
        not_passed(f"derived cost {total_cost:.1f} is not below all_render_cost {cm['all_render_cost']}")
    if total_cost > cm["mixed_cost"] * COST_MARGIN:
        not_passed(f"derived cost {total_cost:.1f} is more than {COST_MARGIN}x the mixed-strategy reference {cm['mixed_cost']}")

    waste_ids = rendered_ids - required_ids
    waste_tolerance = max(20, int(cm["requires_detail_count"] * WASTE_TOLERANCE_FRACTION))
    if len(waste_ids) > waste_tolerance:
        not_passed(
            f"{len(waste_ids)} product(s) with review_count == 0 were rendered anyway "
            f"(tolerance {waste_tolerance}) -- e.g. {sorted(waste_ids)[:5]}"
        )
    return completeness, n_rendered, total_cost


def _check_metrics():
    from prometheus_client import generate_latest
    from prometheus_client.parser import text_string_to_metric_families

    registry = getattr(metrics, "REGISTRY", None)
    if registry is None:
        not_passed("metrics.REGISTRY is still None -- did run_pipeline call metrics.build_registry()?")

    text = generate_latest(registry).decode("utf-8")
    family_names = set()
    samples_by_name = {}
    for fam in text_string_to_metric_families(text):
        family_names.add(fam.name)
        for s in fam.samples:
            samples_by_name.setdefault(s.name, []).append(s)

    missing = REQUIRED_METRIC_FAMILIES - family_names
    if missing:
        not_passed(f"metrics registry is missing required famil{'y' if len(missing) == 1 else 'ies'}: {sorted(missing)}")
    if not (BAN_OR_HONEYPOT_FAMILIES & family_names):
        not_passed("metrics registry must expose at least one of spider_banned / spider_honeypot_hits_total")

    pages = samples_by_name.get("spider_pages_fetched_total", [])
    by_strategy = {s.labels.get("strategy"): s.value for s in pages}
    if by_strategy.get("html", 0) <= 0:
        not_passed(f"spider_pages_fetched_total{{strategy=\"html\"}} did not move (got {by_strategy.get('html')!r})")
    if by_strategy.get("api", 0) <= 0:
        not_passed(f"spider_pages_fetched_total{{strategy=\"api\"}} did not move (got {by_strategy.get('api')!r}) -- the budget router should have rendered several hundred products")

    quarantine_samples = samples_by_name.get("spider_records_quarantined_total", [])
    nonzero_reasons = {s.labels.get("reason") for s in quarantine_samples if s.value > 0}
    if len(nonzero_reasons) < 2:
        not_passed(f"spider_records_quarantined_total only moved for {sorted(nonzero_reasons)} distinct reason(s), need >= 2")

    completeness_samples = samples_by_name.get("spider_field_completeness", [])
    fields = {s.labels.get("field") for s in completeness_samples}
    bad_ratio = [s for s in completeness_samples if not (0.0 <= s.value <= 1.0)]
    if bad_ratio:
        not_passed(f"spider_field_completeness has an out-of-range value: {[(s.labels, s.value) for s in bad_ratio]}")
    if len(fields) < 2:
        not_passed(f"spider_field_completeness only has {sorted(fields)} field label(s), need >= 2")

    count_rows = samples_by_name.get("spider_fetch_latency_seconds_count", [])
    bucket_rows = samples_by_name.get("spider_fetch_latency_seconds_bucket", [])
    sum_rows = samples_by_name.get("spider_fetch_latency_seconds_sum", [])
    if not (count_rows and bucket_rows and sum_rows):
        not_passed("spider_fetch_latency_seconds is missing its _bucket/_count/_sum series -- is it a Histogram?")
    total_latency = sum(s.value for s in count_rows)
    if total_latency <= 0:
        not_passed("spider_fetch_latency_seconds_count is 0 -- no latency observations were recorded")

    return by_strategy, sorted(nonzero_reasons), sorted(fields), total_latency


@guarded
def main():
    gt = load_ground_truth()
    catalog = load_catalog()
    products_by_id = {p["id"]: p for p in catalog["products"]}
    cm = gt["cost_model"]

    bad_by_defect = gt["bad_records"]["by_defect"]
    all_bad_ids = set()
    id_to_defect = {}
    for defect, ids in bad_by_defect.items():
        for i in ids:
            all_bad_ids.add(i)
            id_to_defect[i] = defect

    client_id = f"cp1-capstone-{uuid.uuid4()}"
    reset_client(client_id)
    workdir = TASK_ROOT / "run" / "cp1"

    result = run_pipeline(client_id, day=0, chaos=False, workdir=workdir)
    if not isinstance(result, dict):
        not_passed(f"run_pipeline must return a dict, got {type(result).__name__}")
    _check_result_shape(result)

    id_set = _check_discovery(result, gt)
    violations = _check_client_health(client_id)
    clean_rows, quarantine_rows = _check_gate_split(result, all_bad_ids, id_to_defect)
    checked = _check_field_sample(clean_rows, products_by_id, all_bad_ids)
    completeness, n_rendered, total_cost = _check_budget(clean_rows, quarantine_rows, products_by_id, id_set, cm)
    by_strategy, reasons, fields, total_latency = _check_metrics()

    passed(
        f"{len(id_set)} real ids discovered, 0 honeypots, banned=False, rate_limit_violations={violations}; "
        f"quarantine==exactly {len(all_bad_ids)} bad ids, clean==exactly {len(id_set) - len(all_bad_ids)}; "
        f"{checked} sample fields verified across all 4 markup versions; "
        f"completeness={completeness:.4f} (>= {cm['completeness_target']}), n_rendered={n_rendered}, "
        f"modeled_cost={total_cost:.1f} (all_render={cm['all_render_cost']}, mixed_ref={cm['mixed_cost']}); "
        f"metrics: pages_fetched html={by_strategy.get('html')} api={by_strategy.get('api')}, "
        f"quarantine_reasons={reasons}, completeness_fields={fields}, latency_observations={total_latency:.0f}"
    )


if __name__ == "__main__":
    main()
