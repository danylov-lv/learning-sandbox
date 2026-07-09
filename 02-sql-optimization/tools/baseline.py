"""Machine-local query timing baseline.

All timing checks in this module are RELATIVE to a baseline recorded on the
same machine; there are no absolute-milliseconds assertions anywhere. The
baseline file (baseline-local.json, gitignored) lives in the module root.

Every run executes inside a transaction that is rolled back, so timing
UPDATE-style queries is safe and repeatable.

    uv run python tools/baseline.py record queries/q01.sql
    uv run python tools/baseline.py record queries/q01.sql --id q01 --runs 5
    uv run python tools/baseline.py compare my_rewrite.sql --id q01 --min-speedup 20
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg

MODULE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = MODULE_ROOT / "baseline-local.json"


def conninfo():
    return (
        f"host={os.environ.get('PGHOST', 'localhost')} "
        f"port={os.environ.get('PGPORT', '54302')} "
        f"dbname={os.environ.get('PGDATABASE', 'sandbox')} "
        f"user={os.environ.get('PGUSER', 'sandbox')} "
        f"password={os.environ.get('PGPASSWORD', 'sandbox')}"
    )


def _strip_sql(sql):
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return "\n".join(lines).strip().rstrip(";")


def time_query(sql, runs=5, warmups=1, timeout_ms=600_000):
    """Run sql warmups+runs times (each rolled back); return list of ms."""
    sql = _strip_sql(sql)
    timings = []
    with psycopg.connect(conninfo()) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
            conn.commit()
            for i in range(warmups + runs):
                t0 = time.perf_counter()
                cur.execute(sql)
                if cur.description is not None:
                    cur.fetchall()
                ms = (time.perf_counter() - t0) * 1000
                conn.rollback()
                if i >= warmups:
                    timings.append(ms)
    return timings


def load_baseline(path):
    if Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return {}


def record(sql_file, query_id, runs, baseline_file, timeout_ms):
    sql = Path(sql_file).read_text(encoding="utf-8")
    print(f"recording baseline for '{query_id}' (1 warm-up + {runs} runs)...")
    timings = time_query(sql, runs=runs, timeout_ms=timeout_ms)
    median = statistics.median(timings)
    data = load_baseline(baseline_file)
    data[query_id] = {
        "median_ms": round(median, 2),
        "runs_ms": [round(t, 2) for t in timings],
        "sql_file": str(sql_file),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    Path(baseline_file).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"PASS  baseline '{query_id}' recorded: median {median:.1f} ms "
          f"(runs: {', '.join(f'{t:.1f}' for t in timings)})")
    print(f"      written to {baseline_file}")


def compare(sql_file, query_id, runs, baseline_file, min_speedup, timeout_ms):
    data = load_baseline(baseline_file)
    if query_id not in data:
        print(f"FAIL  no baseline recorded for '{query_id}' in {baseline_file}; "
              f"run 'record' on the original query first")
        sys.exit(2)
    base_ms = data[query_id]["median_ms"]
    sql = Path(sql_file).read_text(encoding="utf-8")
    print(f"comparing against baseline '{query_id}' = {base_ms:.1f} ms "
          f"(1 warm-up + {runs} runs)...")
    timings = time_query(sql, runs=runs, timeout_ms=timeout_ms)
    median = statistics.median(timings)
    speedup = base_ms / median if median > 0 else float("inf")
    line = (f"median {median:.1f} ms vs baseline {base_ms:.1f} ms "
            f"-> speedup {speedup:.1f}x (required >= {min_speedup}x)")
    if speedup >= min_speedup:
        print(f"PASS  {line}")
        sys.exit(0)
    print(f"FAIL  {line}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Record/compare machine-local query timing baselines.")
    sub = ap.add_subparsers(dest="mode", required=True)

    p_rec = sub.add_parser("record", help="record a baseline for a query")
    p_cmp = sub.add_parser("compare", help="compare a (rewritten) query against a baseline")
    for p in (p_rec, p_cmp):
        p.add_argument("sql_file")
        p.add_argument("--id", default=None, help="query id (default: sql file stem)")
        p.add_argument("--runs", type=int, default=5)
        p.add_argument("--baseline-file", default=str(DEFAULT_BASELINE))
        p.add_argument("--timeout-ms", type=int, default=600_000)
    p_cmp.add_argument("--min-speedup", type=float, default=10.0)

    args = ap.parse_args()
    query_id = args.id or Path(args.sql_file).stem

    try:
        if args.mode == "record":
            record(args.sql_file, query_id, args.runs, args.baseline_file, args.timeout_ms)
        else:
            compare(args.sql_file, query_id, args.runs, args.baseline_file,
                    args.min_speedup, args.timeout_ms)
    except psycopg.Error as e:
        print(f"FAIL  database error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
