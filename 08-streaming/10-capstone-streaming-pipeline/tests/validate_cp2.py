"""CP2 validator for 10-capstone-streaming-pipeline: chaos consistency.

Same setup as CP1 (reset topics, produce full corpus, drop all four
tables), then puts the pipeline through TWO distinct failure modes before
checking the exact same aggregate invariants CP1 does:

  (a) An injected mid-stream crash (S07_CRASH_AFTER) -- nonzero exit
      expected and tolerated, same crash hook as task 04/06.
  (b) A forced rebalance -- TWO src/pipeline.py instances launched
      CONCURRENTLY in the same consumer group. The second one joining
      forces redpanda to rebalance partitions between them mid-stream.
      Both must eventually exit 0.
  (c) A final single clean run, to guarantee full completion regardless
      of how the rebalance happened to split partitions between the two
      concurrent instances.
  (d) src/monitor.py run once, checked for a lag snapshot row with
      lag >= 0 -- proof lag monitoring survives all of the above too.

Correctness is judged ONLY on the final aggregate state (via
validate_cp1.verify_all_tables) -- not on any particular partition split
or timing, which is inherently nondeterministic. A category cnt that comes
out too HIGH is called out explicitly as a broken exactly-once path (the
crash or the rebalance caused a redelivered message to be double-applied).

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

from harness.common import guarded, not_passed, passed, pg_connect  # noqa: E402
from validate_cp1 import (  # noqa: E402
    drop_result_tables,
    produce_full_corpus,
    run_pipeline,
    verify_all_tables,
)

PIPELINE_SCRIPT = TASK_ROOT / "src" / "pipeline.py"
MONITOR_SCRIPT = TASK_ROOT / "src" / "monitor.py"

CRASH_AFTER = 60000
CRASH_RUN_TIMEOUT = 300
REBALANCE_RUN_TIMEOUT = 900
FINAL_RUN_TIMEOUT = 600
MONITOR_TIMEOUT = 60


def _last_line(text):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


def _launch_pipeline():
    env = os.environ.copy()
    env.pop("S07_CRASH_AFTER", None)
    return subprocess.Popen(
        ["uv", "run", "python", str(PIPELINE_SCRIPT)],
        cwd=str(TASK_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_concurrent_pair(timeout):
    """Launch two pipeline.py instances at (almost) the same time, in the
    same consumer group -- the second one joining forces a rebalance.
    Returns a list of (returncode, stdout, stderr) once BOTH have exited,
    or None if either did not exit within `timeout` seconds."""
    p1 = _launch_pipeline()
    p2 = _launch_pipeline()

    results = [None, None]
    procs = [p1, p2]
    try:
        for i, p in enumerate(procs):
            out, err = p.communicate(timeout=timeout)
            results[i] = (p.returncode, out, err)
        return results
    except subprocess.TimeoutExpired:
        for p in procs:
            if p.poll() is None:
                p.kill()
                p.communicate()
        return None


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


def fetch_latest_snapshot(conn):
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT MAX(snapshot_id) FROM ops.t10_lag_snapshots")
        except Exception as e:
            return None, f"could not query ops.t10_lag_snapshots -- did monitor.py create it? ({e})"
        snapshot_id = cur.fetchone()[0]
        if snapshot_id is None:
            return None, "ops.t10_lag_snapshots has no rows after monitor.py ran"
        cur.execute(
            "SELECT partition, high_watermark, committed_offset, lag "
            "FROM ops.t10_lag_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        rows = cur.fetchall()
    return rows, None


@guarded
def main():
    if not PIPELINE_SCRIPT.exists():
        not_passed(f"src/pipeline.py not found at {PIPELINE_SCRIPT}")
    if not MONITOR_SCRIPT.exists():
        not_passed(f"src/monitor.py not found at {MONITOR_SCRIPT}")

    gt = produce_full_corpus()

    conn = pg_connect()
    try:
        drop_result_tables(conn)
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS ops.t10_lag_snapshots CASCADE")
        conn.commit()
    finally:
        conn.close()

    # --- (a) injected mid-stream crash. Nonzero exit expected and tolerated.
    r_crash = run_pipeline({"S07_CRASH_AFTER": str(CRASH_AFTER)}, CRASH_RUN_TIMEOUT)
    if r_crash is None:
        not_passed(f"crash run (S07_CRASH_AFTER={CRASH_AFTER}) did not exit within {CRASH_RUN_TIMEOUT}s")
    if r_crash.returncode == 0:
        not_passed(
            f"crash run (S07_CRASH_AFTER={CRASH_AFTER}) exited 0 -- expected a nonzero exit from "
            f"the injected os._exit(1) crash hook; is pipeline.py calling _maybe_crash? "
            f"{_last_line(r_crash.stderr or r_crash.stdout)}"
        )

    # --- (b) two concurrent instances, same group -> forced rebalance.
    pair = run_concurrent_pair(REBALANCE_RUN_TIMEOUT)
    if pair is None:
        not_passed(
            f"the two concurrent pipeline.py instances did not both exit within "
            f"{REBALANCE_RUN_TIMEOUT}s -- did a rebalance leave one of them stuck?"
        )
    for i, (rc, out, err) in enumerate(pair, start=1):
        if rc != 0:
            not_passed(
                f"concurrent instance #{i} exited {rc} -- {_last_line(err or out)}. Two instances in "
                "the same consumer group must both reach idle-exit cleanly despite the rebalance "
                "triggered when the second one joined."
            )

    # --- (c) final single clean run, to guarantee completion regardless of
    # how the rebalance happened to split partitions between (b)'s pair.
    r_final = run_pipeline({}, FINAL_RUN_TIMEOUT)
    if r_final is None:
        not_passed(f"final clean run did not exit within {FINAL_RUN_TIMEOUT}s")
    if r_final.returncode != 0:
        not_passed(f"final clean run exited {r_final.returncode} -- {_last_line(r_final.stderr or r_final.stdout)}")

    # --- (d) lag monitoring survives all of the above.
    r_monitor = run_monitor()
    if r_monitor is None:
        not_passed(f"monitor.py did not exit within {MONITOR_TIMEOUT}s")
    if r_monitor.returncode != 0:
        not_passed(f"monitor.py exited {r_monitor.returncode} -- {_last_line(r_monitor.stderr or r_monitor.stdout)}")

    conn = pg_connect()
    try:
        snapshot_rows, snapshot_err = fetch_latest_snapshot(conn)
        if snapshot_err:
            not_passed(snapshot_err)
        if any(row[3] < 0 for row in snapshot_rows):
            not_passed(f"lag snapshot has a negative lag value: {snapshot_rows}")

        failures = verify_all_tables(conn, gt)
    finally:
        conn.close()

    if failures:
        over_counts = [f for f in failures if "double-counting" in f]
        note = " -- looks like a broken exactly-once path (double-counting under crash/rebalance)" if over_counts else ""
        not_passed(
            "; ".join(failures[:8]) + (f" (+{len(failures) - 8} more)" if len(failures) > 8 else "") + note
        )

    passed(
        "aggregate state matches ground truth exactly after an injected crash, a forced rebalance "
        "between two concurrent instances, and a final clean run; lag snapshot recorded with "
        f"{len(snapshot_rows)} partition row(s), all lag >= 0"
    )


if __name__ == "__main__":
    main()
