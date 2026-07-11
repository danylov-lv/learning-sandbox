"""CP2 validator for 08-capstone-converge: chaos consistency.

Same clean-slate setup as CP1, then puts the pipeline through:

  (a) An injected mid-stream crash during initial snapshot consumption
      (S08_CRASH_AFTER=9000) -- nonzero exit expected and tolerated.
  (b) A mid-stream additive schema change on the SOURCE:
      ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5,2),
      with the connector still running.
  (c) A deterministic burst that sets discount_pct on a batch of existing
      offers and inserts a few new ones with discount_pct populated, plus
      a second deterministic insert/update/delete burst via build_workload.
  (d) A second injected crash (S08_CRASH_AFTER=20000) while catching up
      with that burst -- nonzero exit expected and tolerated.
  (e) One src/monitor.py run, checked for a lag snapshot row.
  (f) A final clean pipeline.py run to guarantee full completion.

Then asserts the SAME convergence invariants CP1 does (via
validate_cp1.check_converged / count_non_tombstone_events), this time
including discount_pct, and that applied_changes was not double-counted
across the two crashes.

Run from this task's directory:

    uv run python tests/validate_cp2.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "tests"))

from harness.common import guarded, mart_connect, not_passed, passed, source_connect  # noqa: E402
from generate import build_workload  # noqa: E402
from validate_cp1 import (  # noqa: E402
    PIPELINE_SCRIPT,
    apply_workload,
    check_converged,
    count_non_tombstone_events,
    drop_result_tables,
    ensure_source_seeded,
    fetch_applied_changes,
    full_cleanup,
    register_cap_connector,
    restore_source_schema,
    run_pipeline,
    teardown_connector,
)

MONITOR_SCRIPT = TASK_ROOT / "src" / "monitor.py"

CRASH_1_AFTER = 9000
# Second crash fires while catching up on the burst in a resumed run whose
# per-run processed-counter restarts at 0. After crash 1 commits ~9000
# offsets, only ~13k messages remain for run 2, so this threshold must sit
# comfortably below that (same reasoning as task 06's CRASH_AFTER_2=10000).
CRASH_2_AFTER = 10000
CRASH_RUN_TIMEOUT = 300
BURST_RUN_TIMEOUT = 600
FINAL_RUN_TIMEOUT = 600
MONITOR_TIMEOUT = 60

DISCOUNT_OFFER_IDS = list(range(1, 41))  # deterministic: offers 1..40
DISCOUNT_INSERT_BASE = 2_000_000

WORKLOAD_SEED = 102
WORKLOAD_N_INSERT = 600
WORKLOAD_N_UPDATE = 1200
WORKLOAD_N_DELETE = 300


def _last_line(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def evolve_schema():
    conn = source_connect()
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE shop.offers ADD COLUMN discount_pct NUMERIC(5, 2)")
        conn.commit()
    finally:
        conn.close()


def apply_discount_burst():
    """Deterministic: sets discount_pct on offers 1..40 (formula on
    offer_id, no randomness needed) and inserts a handful of brand new
    offers that already carry discount_pct -- both cases the pipeline must
    pick up via after.get("discount_pct") once the ALTER above has landed."""
    conn = source_connect()
    try:
        cur = conn.cursor()
        for offer_id in DISCOUNT_OFFER_IDS:
            pct = round((offer_id * 3.7) % 45.0, 2)
            cur.execute(
                "UPDATE shop.offers SET discount_pct = %s, updated_at = now() WHERE offer_id = %s",
                (pct, offer_id),
            )
        for i in range(5):
            offer_id = DISCOUNT_INSERT_BASE + i
            pct = round((i + 1) * 5.5, 2)
            cur.execute(
                "INSERT INTO shop.offers "
                "(offer_id, product_id, seller, price, currency, in_stock, discount_pct, updated_at) "
                "VALUES (%s, 1, 'NovaMarket', 19.99, 'USD', true, %s, now())",
                (offer_id, pct),
            )
        conn.commit()
    finally:
        conn.close()


def run_monitor(timeout=MONITOR_TIMEOUT):
    env = os.environ.copy()
    try:
        return subprocess.run(
            ["uv", "run", "python", str(MONITOR_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def fetch_latest_snapshot_rows():
    conn = mart_connect()
    try:
        cur = conn.cursor()
        try:
            cur.execute("SELECT MAX(snapshot_id) FROM ops.cap_lag_snapshots")
        except Exception as e:
            return None, f"could not query ops.cap_lag_snapshots -- did monitor.py create it? ({e})"
        snapshot_id = cur.fetchone()[0]
        if snapshot_id is None:
            return None, "ops.cap_lag_snapshots has no rows after monitor.py ran"
        cur.execute(
            "SELECT partition, consumer_lag, slot_lag_bytes FROM ops.cap_lag_snapshots "
            "WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        return cur.fetchall(), None
    finally:
        conn.close()


@guarded
def main():
    if not PIPELINE_SCRIPT.exists():
        not_passed(f"src/pipeline.py not found at {PIPELINE_SCRIPT}")
    if not MONITOR_SCRIPT.exists():
        not_passed(f"src/monitor.py not found at {MONITOR_SCRIPT}")

    teardown_connector()
    drop_result_tables()
    restore_source_schema()
    ensure_source_seeded()

    register_cap_connector()

    # --- (a) crash mid-snapshot. Nonzero exit expected and tolerated.
    r_crash1 = run_pipeline({"S08_CRASH_AFTER": str(CRASH_1_AFTER)}, CRASH_RUN_TIMEOUT)
    if r_crash1 is None:
        not_passed(f"first crash run (S08_CRASH_AFTER={CRASH_1_AFTER}) did not exit within {CRASH_RUN_TIMEOUT}s")
    if r_crash1.returncode == 0:
        not_passed(
            f"first crash run exited 0 -- expected a nonzero exit from the injected crash hook; "
            f"is pipeline.py calling _maybe_crash? {_last_line(r_crash1.stderr or r_crash1.stdout)}"
        )

    # --- (b) mid-stream additive schema change, connector still running.
    evolve_schema()

    # --- (c) deterministic bursts, including discount_pct values.
    apply_discount_burst()
    ops = build_workload(
        seed=WORKLOAD_SEED,
        n_insert=WORKLOAD_N_INSERT,
        n_update=WORKLOAD_N_UPDATE,
        n_delete=WORKLOAD_N_DELETE,
    )
    apply_workload(ops)

    # --- (d) second crash while catching up with the burst.
    r_crash2 = run_pipeline({"S08_CRASH_AFTER": str(CRASH_2_AFTER)}, BURST_RUN_TIMEOUT)
    if r_crash2 is None:
        not_passed(f"second crash run (S08_CRASH_AFTER={CRASH_2_AFTER}) did not exit within {BURST_RUN_TIMEOUT}s")
    if r_crash2.returncode == 0:
        not_passed(
            f"second crash run exited 0 -- expected a nonzero exit from the injected crash hook; "
            f"{_last_line(r_crash2.stderr or r_crash2.stdout)}"
        )

    # --- (e) lag monitoring survives the chaos too.
    r_monitor = run_monitor()
    if r_monitor is None:
        not_passed(f"monitor.py did not exit within {MONITOR_TIMEOUT}s")
    if r_monitor.returncode != 0:
        not_passed(f"monitor.py exited {r_monitor.returncode} -- {_last_line(r_monitor.stderr or r_monitor.stdout)}")

    snapshot_rows, snapshot_err = fetch_latest_snapshot_rows()
    if snapshot_err:
        not_passed(snapshot_err)

    # --- (f) final clean run, to guarantee completion regardless of exactly
    # where the two crashes landed.
    r_final = run_pipeline({}, FINAL_RUN_TIMEOUT)
    if r_final is None:
        not_passed(f"final clean run did not exit within {FINAL_RUN_TIMEOUT}s")
    if r_final.returncode != 0:
        not_passed(f"final clean run exited {r_final.returncode} -- {_last_line(r_final.stderr or r_final.stdout)}")

    problem = check_converged(include_discount=True)
    if problem is not None:
        full_cleanup()
        not_passed(f"after crash + schema evolution + burst + crash + final run: {problem}")

    expected_changes = count_non_tombstone_events()
    applied_changes = fetch_applied_changes()
    if applied_changes is None:
        full_cleanup()
        not_passed("mart.cap_meta has no row with id=1")
    if applied_changes != expected_changes:
        full_cleanup()
        direction = "over" if applied_changes > expected_changes else "under"
        note = " -- looks like a broken exactly-once path (double-counting across the two crashes)" if direction == "over" else ""
        not_passed(
            f"mart.cap_meta.applied_changes={applied_changes}, expected {expected_changes} "
            f"(independently drained non-tombstone event count){note}"
        )

    full_cleanup()

    passed(
        f"replica.offers (incl. discount_pct) converged with shop.offers after two injected crashes, "
        f"a mid-stream additive schema change, and two bursts; mart.cap_meta.applied_changes="
        f"{applied_changes} matches drained non-tombstone count exactly; lag snapshot recorded with "
        f"{len(snapshot_rows)} partition row(s)"
    )


if __name__ == "__main__":
    main()
