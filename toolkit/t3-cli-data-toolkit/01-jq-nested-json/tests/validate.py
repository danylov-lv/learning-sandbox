"""Validator for 01-jq-nested-json. Run from the module root:

    cd toolkit/t3-cli-data-toolkit
    uv run python 01-jq-nested-json/tests/validate.py

Runs src/solve.sh, parses its stdout as JSON, and compares it against an
independent recomputation from catalog.json + sources.json performed here
in plain Python -- never against a re-run of the learner's own jq.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    check_close,
    guarded,
    not_passed,
    parse_json_stdout,
    passed,
    require_data,
    run_script,
)

TIERS = ["gold", "silver", "bronze"]


def _expected(catalog: dict, sources: list) -> dict:
    tier_by_source = {s["source_id"]: s["tier"] for s in sources}

    by_category: dict = {}
    for page in catalog["pages"]:
        tier = tier_by_source[page["source_id"]]
        for listing in page["listings"]:
            cat = listing["category"]
            entry = by_category.setdefault(
                cat, {"count": 0, "price_sum": 0.0, "tier_counts": {t: 0 for t in TIERS}}
            )
            entry["count"] += 1
            entry["price_sum"] += listing["price_cents"] / 100
            entry["tier_counts"][tier] += 1

    return by_category


@guarded
def main() -> None:
    catalog_path = require_data("scraped", "catalog.json")
    sources_path = require_data("scraped", "sources.json")

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sources = json.loads(sources_path.read_text(encoding="utf-8"))

    expected = _expected(catalog, sources)

    result = run_script(TASK_DIR / "src" / "solve.sh")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        not_passed(f"src/solve.sh exited {result.returncode}: {tail}")

    actual = parse_json_stdout(result, label="src/solve.sh")

    if not isinstance(actual, list):
        not_passed(f"src/solve.sh must print a JSON array, got {type(actual).__name__}")

    actual_by_category = {}
    for i, obj in enumerate(actual):
        if not isinstance(obj, dict) or "category" not in obj:
            not_passed(f"element {i} of the output array is not an object with a 'category' key")
        cat = obj["category"]
        if cat in actual_by_category:
            not_passed(f"category '{cat}' appears more than once in the output")
        actual_by_category[cat] = obj

    missing = set(expected) - set(actual_by_category)
    extra = set(actual_by_category) - set(expected)
    if missing:
        not_passed(f"missing categor{'y' if len(missing) == 1 else 'ies'}: {sorted(missing)}")
    if extra:
        not_passed(f"unexpected categor{'y' if len(extra) == 1 else 'ies'} in output: {sorted(extra)}")

    for cat, exp in expected.items():
        obj = actual_by_category[cat]

        if "listing_count" not in obj:
            not_passed(f"category '{cat}': missing 'listing_count'")
        if obj["listing_count"] != exp["count"]:
            not_passed(f"category '{cat}': listing_count got {obj['listing_count']}, expected {exp['count']}")

        if "avg_price_usd" not in obj:
            not_passed(f"category '{cat}': missing 'avg_price_usd'")
        expected_avg = exp["price_sum"] / exp["count"]
        check_close(obj["avg_price_usd"], expected_avg, rel_tol=1e-6, label=f"category '{cat}' avg_price_usd")

        tier_counts = obj.get("tier_counts")
        if not isinstance(tier_counts, dict):
            not_passed(f"category '{cat}': 'tier_counts' must be an object")
        for tier in TIERS:
            if tier not in tier_counts:
                not_passed(f"category '{cat}': tier_counts missing key '{tier}'")
            if tier_counts[tier] != exp["tier_counts"][tier]:
                not_passed(
                    f"category '{cat}': tier_counts['{tier}'] got {tier_counts[tier]}, "
                    f"expected {exp['tier_counts'][tier]}"
                )

    passed(f"{len(expected)} categories verified")


if __name__ == "__main__":
    main()
