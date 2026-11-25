"""Machine-local timing baseline for s09.t07 -- run this AFTER `ch_answer` and
`duck_answer` in `src/bench.py` both work.

Opens a live ClickHouse client and a DuckDB connection, times each answer
function with `harness.common.time_it`, prints both elapsed times and the
ratio, and writes them to a gitignored `baseline-local.json` next to this
file (via `harness.common.write_baseline`) so `tests/validate.py` can read
them back later. Timing here is informational -- it does not check
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

from harness.common import ch_client, duckdb_connect, time_it, write_baseline  # noqa: E402
from src.bench import ch_answer, duck_answer  # noqa: E402

BASELINE_PATH = TASK_ROOT / "baseline-local.json"


def main():
    try:
        client = ch_client()
        con = duckdb_connect()
    except SystemExit:
        print("Could not reach the live stack -- is `docker compose up -d` running?")
        sys.exit(1)

    try:
        try:
            _, ch_seconds = time_it(ch_answer, client)
            _, duck_seconds = time_it(duck_answer, con)
        except NotImplementedError:
            print(
                "ch_answer() / duck_answer() still raise NotImplementedError -- "
                "implement both in src/bench.py, then re-run this script."
            )
            sys.exit(1)

        ratio = ch_seconds / duck_seconds if duck_seconds > 0 else float("inf")

        print(f"ch_seconds:   {ch_seconds:.4f}")
        print(f"duck_seconds: {duck_seconds:.4f}")
        print(f"ratio (ch_seconds / duck_seconds): {ratio:.2f}x")

        path = write_baseline(
            BASELINE_PATH,
            {"ch_seconds": ch_seconds, "duck_seconds": duck_seconds, "ratio": ratio},
        )
        print(f"wrote baseline to {path}")
    finally:
        client.close()
        con.close()


if __name__ == "__main__":
    main()
