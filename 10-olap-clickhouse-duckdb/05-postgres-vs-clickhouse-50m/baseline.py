"""Machine-local timing baseline for s09.t05 -- run this AFTER `pg_answer` and
`ch_answer` in `src/compare.py` both work.

Opens a live Postgres connection and ClickHouse client, times each answer
function with `harness.common.time_it`, prints both elapsed times and the
speedup ratio, and writes them to a gitignored `baseline-local.json` next to
this file (via `harness.common.write_baseline`) so `tests/validate.py` can
read them back later. Timing here is informational -- it does not check
correctness; that's `tests/validate.py`'s job.

Tolerates a still-NotImplementedError scaffold gracefully: prints a friendly
message and exits, no traceback.

    uv run python baseline.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parent
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import ch_client, pg_connect, time_it, write_baseline  # noqa: E402
from src.compare import ch_answer, pg_answer  # noqa: E402

BASELINE_PATH = TASK_ROOT / "baseline-local.json"


def main():
    try:
        conn = pg_connect()
        client = ch_client()
    except SystemExit:
        print("Could not reach the live stack -- is `docker compose up -d` running?")
        sys.exit(1)

    try:
        try:
            _, pg_seconds = time_it(pg_answer, conn)
            _, ch_seconds = time_it(ch_answer, client)
        except NotImplementedError:
            print(
                "pg_answer() / ch_answer() still raise NotImplementedError -- "
                "implement both in src/compare.py, then re-run this script."
            )
            sys.exit(1)

        ratio = pg_seconds / ch_seconds if ch_seconds > 0 else float("inf")

        print(f"pg_seconds:  {pg_seconds:.4f}")
        print(f"ch_seconds:  {ch_seconds:.4f}")
        print(f"speedup (pg_seconds / ch_seconds): {ratio:.2f}x")

        path = write_baseline(BASELINE_PATH, {"pg_seconds": pg_seconds, "ch_seconds": ch_seconds, "ratio": ratio})
        print(f"wrote baseline to {path}")
    finally:
        conn.close()
        client.close()


if __name__ == "__main__":
    main()
