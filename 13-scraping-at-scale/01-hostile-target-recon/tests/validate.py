"""Validator for 13-scraping-at-scale task 01 -- hostile-target-recon.

Drives the learner's src/recon.py against the LIVE hostile target (assumes
the docker stack is already up -- `docker compose up -d` at the module
root). The oracle is computed INDEPENDENTLY from
`harness.common.load_ground_truth()` / `load_catalog()` and the target's own
`/__debug/client` state -- never by trusting the learner's crawl output as
truth.

Checks:
  1. Fresh client id, reset via `harness.common.reset_client`.
  2. Call the learner's `crawl_catalog(client_id, day=0)` ONCE -- the full
     crawl is the expensive part (~85s at a polite pace against this
     target's tuned rate limit); this validator does not repeat it.
  3. The returned record ids must equal EXACTLY the real product id set
     (`1..n_products` from ground truth) -- a count check, a duplicate
     check, and an exact-set check, with an explicit assertion that no
     honeypot id (`n_products+1..n_products+30`) is present.
  4. `/__debug/client` for that client_id must show `banned=False`,
     `honeypot_hits=0`, `header_rejections=0`, and `rate_limit_violations`
     within a small tolerance (a few 429s handled via backoff are fine, a
     ban is not).
  5. Spot-check a sample of clean (non-bad-record) ids spread across the id
     range against `harness.common.load_catalog()`'s day-0 baseline:
     title/price(tol 0.01)/currency/in_stock/review_count must match, and
     `rating`/`shipping_info` must be populated wherever `review_count > 0`
     -- proving the learner actually called the JS-only
     `GET /api/product/{id}` endpoint rather than only scraping HTML.
  6. RECON.md must be filled in: all 4 section headings present, the
     shipped "[fill in" placeholder gone, a minimum content length per
     section, and enough of the expected keywords mentioned.

Run from the module root:

    uv run python 01-hostile-target-recon/tests/validate.py
"""

import re
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
from src.recon import crawl_catalog  # noqa: E402

PRICE_TOLERANCE = 0.01
RATING_TOLERANCE = 0.05
MAX_RATE_LIMIT_VIOLATIONS = 10  # a few 429s handled via backoff are fine, a ban is not
SAMPLE_SIZE = 40
MIN_SAMPLE_CHECKED = SAMPLE_SIZE // 2

RECON_PATH = TASK_ROOT / "RECON.md"
REQUIRED_HEADINGS = [
    "## Header/fingerprint gate",
    "## Rate limiting",
    "## Honeypots",
    "## JS-only fields",
]
PLACEHOLDER_MARKER = "[fill in"
MIN_SECTION_CONTENT = 120

GROUNDING_KEYWORDS = {
    "honeypot": ["honeypot", "trap", "display:none", "nofollow"],
    "rate_limit": ["rate limit", "token bucket", "429", "throttle", "pacing", "pace"],
    "header": ["user-agent", "user agent", "accept-language", "header"],
    "js_api": ["/api/product", "api/product", "js-only", "javascript", "headless", "xhr"],
}
MIN_GROUNDING_HITS = 4


def _extract_section(text, heading):
    idx = text.find(heading)
    if idx == -1:
        return None
    rest = text[idx + len(heading):]
    m = re.search(r"\n##\s", rest)
    return rest[: m.start()] if m else rest


def _check_recon_md():
    if not RECON_PATH.exists():
        not_passed(f"RECON.md not found at {RECON_PATH}")
    text = RECON_PATH.read_text(encoding="utf-8")

    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing:
        not_passed(f"RECON.md missing required section heading(s): {missing}")

    for heading in REQUIRED_HEADINGS:
        content = _extract_section(text, heading)
        name = heading.replace("## ", "")
        if content is None:
            not_passed(f"RECON.md: could not find content for section '{name}'")
        if PLACEHOLDER_MARKER in content:
            not_passed(f"RECON.md: section '{name}' still contains the shipped '[fill in' placeholder")
        stripped_len = len(content.strip())
        if stripped_len < MIN_SECTION_CONTENT:
            not_passed(
                f"RECON.md: section '{name}' has only {stripped_len} chars of content, "
                f"expected at least {MIN_SECTION_CONTENT} (looks unfilled)"
            )

    text_lower = text.lower()
    hits = [k for k, variants in GROUNDING_KEYWORDS.items() if any(v in text_lower for v in variants)]
    if len(hits) < MIN_GROUNDING_HITS:
        missing_concepts = sorted(set(GROUNDING_KEYWORDS) - set(hits))
        not_passed(
            f"RECON.md only references {len(hits)}/{len(GROUNDING_KEYWORDS)} expected concepts "
            f"(missing: {missing_concepts}) -- describe each defense concretely, not in general terms"
        )


def _sample_ids(gt):
    """Clean (non-bad-record), non-honeypot ids spread evenly across the
    range -- bad-record ids are deliberately excluded here because their
    price/title/currency are supposed to differ from the catalog baseline
    (that's task 02's problem, not this one's)."""
    bad_ids = set()
    for ids in gt["bad_records"]["by_defect"].values():
        bad_ids.update(ids)
    n = gt["n_products"]
    clean_ids = [i for i in range(1, n + 1) if i not in bad_ids]
    step = max(1, len(clean_ids) // SAMPLE_SIZE)
    return clean_ids[::step][:SAMPLE_SIZE]


@guarded
def main():
    gt = load_ground_truth()
    catalog = load_catalog()
    catalog_by_id = {p["id"]: p for p in catalog["products"]}

    client_id = f"recon-validate-{uuid.uuid4()}"
    reset_client(client_id)

    records = crawl_catalog(client_id, day=0)

    if not isinstance(records, list):
        not_passed(f"crawl_catalog returned {type(records).__name__}, expected a list of dicts")

    n_products = gt["n_products"]
    honeypot_ids = set(gt["honeypot_ids"])

    ids_seen = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or "id" not in rec:
            not_passed(f"crawl_catalog record {i} is malformed: {rec!r}")
        ids_seen.append(int(rec["id"]))

    id_set = set(ids_seen)
    expected_ids = set(range(1, n_products + 1))

    if len(ids_seen) != len(id_set):
        not_passed(
            f"crawl_catalog returned {len(ids_seen) - len(id_set)} duplicate id(s) -- "
            f"each real product must appear exactly once"
        )

    if len(id_set) != n_products:
        not_passed(f"crawl_catalog returned {len(id_set)} distinct ids, ground truth expects {n_products}")

    honeypots_returned = id_set & honeypot_ids
    if honeypots_returned:
        not_passed(
            f"crawl_catalog returned {len(honeypots_returned)} honeypot id(s), e.g. "
            f"{sorted(honeypots_returned)[:5]} -- these must be excluded, never followed"
        )

    if id_set != expected_ids:
        missing = sorted(expected_ids - id_set)[:5]
        extra = sorted(id_set - expected_ids)[:5]
        not_passed(
            f"crawl_catalog id set does not match the real product range 1..{n_products}: "
            f"missing e.g. {missing}, extra e.g. {extra}"
        )

    state = get_client_state(client_id)
    if state.get("banned"):
        not_passed(f"client {client_id} got BANNED during the crawl -- state: {state}")
    if state.get("honeypot_hits", 0) != 0:
        not_passed(f"client hit {state['honeypot_hits']} honeypot(s) during the crawl -- state: {state}")
    if state.get("header_rejections", 0) != 0:
        not_passed(
            f"client got {state['header_rejections']} header rejection(s) -- check that every "
            f"request sends User-Agent containing 'Mozilla/5.0' and a non-blank Accept-Language: {state}"
        )
    violations = state.get("rate_limit_violations", 0)
    if violations > MAX_RATE_LIMIT_VIOLATIONS:
        not_passed(
            f"client racked up {violations} rate-limit violations (429s), expected <= "
            f"{MAX_RATE_LIMIT_VIOLATIONS} -- a polite crawler paces its dispatch rate explicitly, "
            f"it doesn't rely on 429 backoff as its primary rate control: {state}"
        )

    # --- Spot-check a sample of clean records against the independent catalog oracle ---
    records_by_id = {int(r["id"]): r for r in records}
    sample_ids = _sample_ids(gt)
    checked = 0
    for pid in sample_ids:
        oracle = catalog_by_id.get(pid)
        if oracle is None:
            continue
        rec = records_by_id.get(pid)
        if rec is None:
            not_passed(f"product {pid} missing from crawl_catalog's output despite being a real, clean id")

        if rec.get("title") != oracle["title"]:
            not_passed(f"product {pid}: title={rec.get('title')!r}, oracle expected {oracle['title']!r}")
        price = rec.get("price")
        if price is None or abs(float(price) - float(oracle["price"])) > PRICE_TOLERANCE:
            not_passed(f"product {pid}: price={price!r}, oracle expected ~{oracle['price']} (tol {PRICE_TOLERANCE})")
        if rec.get("currency") != oracle["currency"]:
            not_passed(f"product {pid}: currency={rec.get('currency')!r}, oracle expected {oracle['currency']!r}")
        if bool(rec.get("in_stock")) != bool(oracle["in_stock"]):
            not_passed(f"product {pid}: in_stock={rec.get('in_stock')!r}, oracle expected {oracle['in_stock']!r}")
        if int(rec.get("review_count", -1)) != int(oracle["review_count"]):
            not_passed(
                f"product {pid}: review_count={rec.get('review_count')!r}, oracle expected {oracle['review_count']!r}"
            )

        if oracle["review_count"] > 0:
            rating = rec.get("rating")
            if rating is None:
                not_passed(
                    f"product {pid}: review_count={oracle['review_count']} > 0 but rating is missing -- "
                    f"did you call GET /api/product/{{id}}?"
                )
            if abs(float(rating) - float(oracle["rating"])) > RATING_TOLERANCE:
                not_passed(f"product {pid}: rating={rating!r}, oracle expected ~{oracle['rating']} (tol {RATING_TOLERANCE})")

            shipping = rec.get("shipping_info")
            if not isinstance(shipping, dict):
                not_passed(
                    f"product {pid}: review_count={oracle['review_count']} > 0 but shipping_info is "
                    f"missing/not an object -- did you call GET /api/product/{{id}}?"
                )
            if bool(shipping.get("free")) != bool(oracle["shipping_free"]):
                not_passed(f"product {pid}: shipping_info.free={shipping.get('free')!r}, oracle expected {oracle['shipping_free']!r}")
            if int(shipping.get("eta_days", -1)) != int(oracle["shipping_eta_days"]):
                not_passed(
                    f"product {pid}: shipping_info.eta_days={shipping.get('eta_days')!r}, "
                    f"oracle expected {oracle['shipping_eta_days']!r}"
                )
            if shipping.get("carrier") != oracle["shipping_carrier"]:
                not_passed(
                    f"product {pid}: shipping_info.carrier={shipping.get('carrier')!r}, "
                    f"oracle expected {oracle['shipping_carrier']!r}"
                )

        checked += 1

    if checked < MIN_SAMPLE_CHECKED:
        not_passed(f"only {checked} sample products were checkable (expected around {SAMPLE_SIZE}) -- sampling logic may be broken")

    _check_recon_md()

    passed(
        f"{len(id_set)} real product ids discovered, 0 honeypots followed; "
        f"client state banned=False honeypot_hits=0 header_rejections=0 rate_limit_violations={violations}; "
        f"{checked} sample records verified vs catalog oracle (title/price/currency/in_stock/review_count "
        f"+ js-only rating/shipping_info); RECON.md complete"
    )


if __name__ == "__main__":
    main()
