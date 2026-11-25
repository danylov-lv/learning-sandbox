"""GIVEN drill tool for CP2 — do not edit, do not read this for "the answer."

Synthesizes data/raw/dt=2025-06-15/prices.ndjson from dt=2025-06-14's file:

  - every parseable line's `scraped_at` is shifted forward exactly one day
    (so the synthesized day is internally consistent: records that were
    valid on 06-14 are valid on 06-15, records whose timestamps were
    out-of-window stay out-of-window);
  - a fixed-seed ~40% sample of parseable lines has the `currency` key
    renamed to `currency_code` — a schema change no prior task in this
    module covered. Your v3 contract expects `currency`; ~40% of this
    day's records no longer have it;
  - malformed lines are copied byte-for-byte, unchanged — they should be
    quarantined at ingest for the same reason they always are.

This script creates ONLY an input state — a new raw day file plus a
manifest recording exactly what it planted. It contains no pipeline logic
and no assertions about your DAG. `validate_cp2.py` reads the manifest
this script writes and checks your pipeline's *output* against it.

Determinism: given the same dt=2025-06-14 source file, this script
produces byte-identical output and an identical manifest on every run
(fixed seed; `generated_at` in the manifest is the only field that
legitimately changes between runs).

Usage (from this task's directory):

    uv run python tests/drill_new_drift.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import load_ground_truth, not_passed, raw_day_file  # noqa: E402

SEED = 150615
RENAME_FRACTION = 0.4
SOURCE_DT = "2025-06-14"
TARGET_DT = "2025-06-15"
MANIFEST_PATH = TASK_ROOT / "tests" / "drift-manifest-local.json"


def _shift_scraped_at(value: str) -> str:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (ts + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dedup_key(record: dict):
    return (
        record.get("source_site"),
        record.get("product_url"),
        record.get("scraped_at"),
    )


def main():
    import numpy as np

    source_path = raw_day_file(SOURCE_DT)
    if not source_path.exists():
        not_passed(f"source file not found: {source_path} — is data/raw/ populated?")

    target_path = raw_day_file(TARGET_DT)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    raw_lines = source_path.read_bytes().split(b"\n")
    if raw_lines and raw_lines[-1] == b"":
        raw_lines = raw_lines[:-1]

    parseable_idx = []
    parsed = [None] * len(raw_lines)
    for i, line in enumerate(raw_lines):
        try:
            parsed[i] = json.loads(line)
            parseable_idx.append(i)
        except json.JSONDecodeError:
            parsed[i] = None

    parseable_count = len(parseable_idx)
    rename_count = round(parseable_count * RENAME_FRACTION)

    rng = np.random.default_rng(SEED)
    rename_idx = set(rng.choice(parseable_idx, size=rename_count, replace=False).tolist())

    out_lines = []
    renamed_actual = 0
    key_rename_flags: dict = {}
    for i, line in enumerate(raw_lines):
        record = parsed[i]
        if record is None:
            out_lines.append(line)
            continue

        if isinstance(record.get("scraped_at"), str):
            record["scraped_at"] = _shift_scraped_at(record["scraped_at"])

        is_renamed = i in rename_idx and "currency" in record
        if is_renamed:
            record["currency_code"] = record.pop("currency")
            renamed_actual += 1

        key = _dedup_key(record)
        key_rename_flags.setdefault(key, []).append(is_renamed)

        out_lines.append(json.dumps(record, ensure_ascii=False).encode("utf-8"))

    target_path.write_bytes(b"\n".join(out_lines) + b"\n")

    keys_total = len(key_rename_flags)
    keys_fully_renamed = sum(1 for flags in key_rename_flags.values() if all(flags))
    keys_with_survivor = keys_total - keys_fully_renamed

    gt = load_ground_truth()
    gt_day = gt["per_day"][SOURCE_DT]
    invalid_total = gt_day["invalid_records"]["total"]
    duplicate_lines = gt_day["duplicate_lines"]

    manifest = {
        "source_dt": SOURCE_DT,
        "target_dt": TARGET_DT,
        "seed": SEED,
        "rename_fraction": RENAME_FRACTION,
        "total_lines": len(raw_lines),
        "malformed_lines": len(raw_lines) - parseable_count,
        "parseable_lines": parseable_count,
        "renamed_count": renamed_actual,
        "dedup_keys_total": keys_total,
        "keys_fully_renamed": keys_fully_renamed,
        "keys_with_survivor": keys_with_survivor,
        "gt_invalid_records_source_day": invalid_total,
        "gt_duplicate_lines_source_day": duplicate_lines,
        # Expected pipeline outcome for dt=2025-06-15, derived from the plant:
        # rows reaching core = distinct valid dedup keys with >= 1 unrenamed
        # copy. Validity status is identical to the source day's records, so
        # the count is bounded by keys_with_survivor from above and by
        # keys_with_survivor minus all of the source day's invalid records
        # from below.
        "expected_core_count_min": keys_with_survivor - invalid_total,
        "expected_core_count_max": keys_with_survivor,
        # stage='contract' quarantine rows: at least one per dedup key whose
        # every copy lost `currency` (those can never load), at most every
        # renamed line plus the day's own invalid records plus duplicates
        # (if the learner's gate runs before dedup and quarantines per line).
        "expected_contract_quarantine_min": keys_fully_renamed,
        "expected_contract_quarantine_max": renamed_actual + invalid_total + duplicate_lines,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"wrote {target_path}")
    print(f"  total lines                     : {len(raw_lines)}")
    print(f"  malformed (copied unchanged)    : {manifest['malformed_lines']}")
    print(f"  renamed currency->currency_code : {renamed_actual}")
    print(f"  dedup keys fully renamed        : {keys_fully_renamed} (must be quarantined)")
    print(f"  dedup keys with surviving copy  : {keys_with_survivor} (loadable if valid)")
    print(f"  expected core rows for {TARGET_DT}: "
          f"[{manifest['expected_core_count_min']}, {manifest['expected_core_count_max']}]")
    print(f"wrote manifest {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
