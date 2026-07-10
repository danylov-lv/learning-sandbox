"""CP2 validator for 10-capstone-end-to-end: failure drills.

Two independent checks, both required:

--midstate   Re-checks all 14 original CP1 conditions (via
              validate_cp1.verify_days), then additionally checks, using
              tests/midstate-manifest-local.json written by
              drill_break_midstate.py:
                - core.price_records max(loaded_at) for every day NOT in
                  the drill's affected_days is byte-identical to the
                  pre-drill snapshot (i.e. your recovery never re-touched
                  core for a healthy day).
                - core.price_records row counts for every day are
                  unchanged from the pre-drill snapshot (no duplication,
                  affected or not — the drill never deleted core).
                - ops.load_audit has at least one row per affected day with
                  finished_at strictly after the drill's generated_at
                  timestamp (proof a recovery run actually happened), and
                  NO unaffected day has a load_audit row that new — proof
                  the recovery was scoped, not a full re-backfill.

--drift      Using tests/drift-manifest-local.json written by
              drill_new_drift.py:
                - ops.quarantine row count for dt=2025-06-15 with
                  stage='contract' falls inside the manifest's
                  [expected_contract_quarantine_min, _max] band (the band
                  is architecture-agnostic: it admits both dedup-before-
                  contract and contract-before-dedup pipelines).
                - core.price_records for dt=2025-06-15 has a row count
                  inside the manifest's [expected_core_count_min, _max]
                  band (the band's width is the source day's own ~1%
                  invalid-record count, which is unrelated to the drift).
                - an alert with type='contract_drift' and dt/day info
                  matching 2025-06-15 exists in data/alerts/alerts.ndjson.
                - mart.daily_category_prices and the silver lake for
                  2025-06-01..14 are untouched: re-run verify_days over
                  those 14 days and require it to still pass.

Both checks require their manifest to exist (run the corresponding drill
script first) and fail cleanly with NOT PASSED, not a traceback, if it
doesn't.

Run from this task's directory:

    uv run python tests/validate_cp2.py --midstate
    uv run python tests/validate_cp2.py --drift
    uv run python tests/validate_cp2.py            # both, in order
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

sys.path.insert(0, str(TASK_ROOT / "tests"))

from harness.common import (  # noqa: E402
    guarded,
    load_ground_truth,
    not_passed,
    pg_connect,
    read_alerts,
)
from validate_cp1 import _s3_client, verify_days  # noqa: E402

MIDSTATE_MANIFEST = TASK_ROOT / "tests" / "midstate-manifest-local.json"
DRIFT_MANIFEST = TASK_ROOT / "tests" / "drift-manifest-local.json"
DRIFT_DT = "2025-06-15"


def _load_manifest(path):
    if not path.exists():
        not_passed(f"manifest not found at {path} — run the corresponding drill script first")
    return json.loads(path.read_text(encoding="utf-8"))


def check_midstate():
    from datetime import datetime

    manifest = _load_manifest(MIDSTATE_MANIFEST)
    gt = load_ground_truth()
    days = gt["days"]
    affected = set(manifest["affected_days"])
    drill_time = datetime.fromisoformat(manifest["generated_at"])

    conn = pg_connect()
    s3 = _s3_client()

    failures = verify_days(gt, conn, s3, days)

    with conn.cursor() as cur:
        for dt in days:
            cur.execute("SELECT count(*), max(loaded_at) FROM core.price_records WHERE dt = %s", (dt,))
            count, loaded_at = cur.fetchone()
            loaded_at_str = loaded_at.isoformat() if loaded_at else None

            if count != manifest["pre_drill_core_counts"][dt]:
                failures.append(
                    f"{dt}: core row count {count} != pre-drill snapshot {manifest['pre_drill_core_counts'][dt]}"
                )

            if dt not in affected and loaded_at_str != manifest["pre_drill_core_loaded_at"][dt]:
                failures.append(
                    f"{dt}: unaffected day's core.loaded_at changed "
                    f"({manifest['pre_drill_core_loaded_at'][dt]} -> {loaded_at_str}) — "
                    f"recovery touched a healthy day"
                )

            cur.execute(
                "SELECT count(*) FROM ops.load_audit WHERE dt = %s AND finished_at > %s",
                (dt, drill_time),
            )
            new_audit_rows = cur.fetchone()[0]

            if dt in affected and new_audit_rows == 0:
                failures.append(f"{dt}: affected day has no ops.load_audit row after the drill — no recovery run detected")
            if dt not in affected and new_audit_rows > 0:
                failures.append(
                    f"{dt}: unaffected day has {new_audit_rows} new ops.load_audit rows after the drill — "
                    f"recovery was not scoped to the affected days"
                )

    conn.close()

    if failures:
        not_passed("[midstate] " + "; ".join(failures[:8]) + (f" (+{len(failures) - 8} more)" if len(failures) > 8 else ""))
    print("PASSED: midstate recovery — CP1 conditions hold, unaffected days untouched, "
          f"recovery detected for exactly {sorted(affected)}")


def check_drift():
    manifest = _load_manifest(DRIFT_MANIFEST)
    gt = load_ground_truth()
    original_days = gt["days"]

    conn = pg_connect()
    s3 = _s3_client()

    failures = []

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM ops.quarantine WHERE dt = %s AND stage = 'contract'", (DRIFT_DT,))
        quarantined = cur.fetchone()[0]
        q_min = manifest["expected_contract_quarantine_min"]
        q_max = manifest["expected_contract_quarantine_max"]
        if not (q_min <= quarantined <= q_max):
            failures.append(
                f"{DRIFT_DT}: {quarantined} rows quarantined at stage='contract', "
                f"expected between {q_min} and {q_max} (see drill manifest)"
            )

        cur.execute("SELECT count(*) FROM core.price_records WHERE dt = %s", (DRIFT_DT,))
        core_count = cur.fetchone()[0]
        c_min = manifest["expected_core_count_min"]
        c_max = manifest["expected_core_count_max"]
        if not (c_min <= core_count <= c_max):
            failures.append(
                f"{DRIFT_DT}: core row count {core_count}, expected between {c_min} and {c_max} "
                f"(distinct valid records with a surviving `currency` key)"
            )

    conn.close()

    alerts = read_alerts()
    drift_alerts = [
        a for a in alerts
        if a.get("type") == "contract_drift" and DRIFT_DT in json.dumps(a)
    ]
    if not drift_alerts:
        failures.append(f"no type='contract_drift' alert mentioning {DRIFT_DT} found in data/alerts/alerts.ndjson")

    conn2 = pg_connect()
    s3_2 = _s3_client()
    downstream_failures = verify_days(gt, conn2, s3_2, original_days)
    conn2.close()
    if downstream_failures:
        failures.append(
            "downstream days (06-01..14) no longer pass CP1 checks after processing the drift day: "
            + "; ".join(downstream_failures[:4])
        )

    if failures:
        not_passed("[drift] " + "; ".join(failures[:8]) + (f" (+{len(failures) - 8} more)" if len(failures) > 8 else ""))
    print(f"PASSED: drift drill — {DRIFT_DT} contract caught the renamed field "
          f"({quarantined} quarantined, {core_count} loaded), alerted, downstream days untouched")


@guarded
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--midstate", action="store_true")
    parser.add_argument("--drift", action="store_true")
    args = parser.parse_args()

    run_midstate = args.midstate or not (args.midstate or args.drift)
    run_drift = args.drift or not (args.midstate or args.drift)

    if run_midstate:
        check_midstate()
    if run_drift:
        check_drift()


if __name__ == "__main__":
    main()
