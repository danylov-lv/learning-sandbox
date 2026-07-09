"""Benchmark harness for 07-duckdb-taste.

Runs the learner's probe.sql through DuckDB and times it against a naive
full-scan baseline (pyarrow.dataset over the same lake, ignoring hive
partitioning, filtering in Python/compute). Also runs pruning_proof.sql and
parses its EXPLAIN ANALYZE plan to count how many physical Parquet files
DuckDB actually opened, versus the total files in the lake and the total
files physically inside the two partition directories the probe covers.

Writes results-local.json next to this task's README and prints a summary
table. Timing here is informational only -- see tests/validate.py for the
structural (file-count) pruning check that actually gates PASSED.

Run from the module root:
    uv run python 07-duckdb-taste/tests/bench.py
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pyarrow.dataset as ds

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import DATA_DIR, fail, guarded, load_ground_truth  # noqa: E402

QUERIES_DIR = TASK_ROOT / "src" / "queries"
LAKE_DIR = DATA_DIR / "lake"
RESULTS_PATH = TASK_ROOT / "results-local.json"
PROFILE_PATH = TASK_ROOT / "results-local.profile.json"


def strip_sql_comments(text):
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def load_query(name):
    path = QUERIES_DIR / name
    if not path.exists():
        fail(f"missing query file {path}")
    body = strip_sql_comments(path.read_text(encoding="utf-8"))
    if not body:
        fail(f"{name} not implemented yet -- still just the TODO placeholder")
    return body


def covered_months(date_from, date_to):
    d0 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    months = []
    cur = d0.replace(day=1)
    while cur <= d1:
        key = f"{cur.year:04d}-{cur.month:02d}"
        if key not in months:
            months.append(key)
        cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 else cur.replace(month=cur.month + 1)
    return months


def run_probe_duckdb(con, sql_text):
    t0 = time.perf_counter()
    row = con.execute(sql_text).fetchone()
    wall = time.perf_counter() - t0
    if row is None or len(row) < 2:
        fail("probe.sql did not return a (row_count, price_sum) row")
    return {"wall_s": wall, "row_count": row[0], "price_sum": row[1]}


def run_probe_naive(gt):
    fp = gt["filter_probe"]
    dataset = ds.dataset(LAKE_DIR, format="parquet")  # no hive partitioning: every fragment considered
    ts_from = datetime.strptime(fp["captured_at_from"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    ts_to = datetime.strptime(fp["captured_at_to"], "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
    filt = (ds.field("source_id") == fp["source_id"]) & (ds.field("captured_at") >= ts_from) & (ds.field("captured_at") < ts_to)

    t0 = time.perf_counter()
    table = dataset.to_table(filter=filt, columns=["price"])
    wall = time.perf_counter() - t0
    price_sum = float(sum(v for v in table.column("price").to_pylist() if v is not None))
    return {"wall_s": wall, "row_count": table.num_rows, "price_sum": price_sum}


def parse_explain_analyze(con, pruning_proof_body):
    match = re.match(r"(?is)^\s*EXPLAIN\s+ANALYZE\s*(.*)$", pruning_proof_body)
    if not match:
        fail("pruning_proof.sql must start with EXPLAIN ANALYZE")
    inner_sql = match.group(1).strip()
    if not inner_sql:
        fail("pruning_proof.sql has EXPLAIN ANALYZE but no query after it")

    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    con.execute("PRAGMA enable_profiling='json'")
    con.execute(f"PRAGMA profiling_output='{PROFILE_PATH.as_posix()}'")
    try:
        con.execute(inner_sql).fetchall()
    finally:
        con.execute("PRAGMA disable_profiling")

    if not PROFILE_PATH.exists():
        fail("DuckDB did not write a profiling output file -- unexpected duckdb version behavior")
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    PROFILE_PATH.unlink()

    files_read = 0
    found = False

    def walk(node):
        nonlocal files_read, found
        info = node.get("extra_info", {})
        if info.get("Function") == "READ_PARQUET" and "Total Files Read" in info:
            files_read += int(info["Total Files Read"])
            found = True
        for child in node.get("children", []):
            walk(child)

    walk(profile)
    if not found:
        fail("could not find a READ_PARQUET 'Total Files Read' entry in the EXPLAIN ANALYZE plan")
    return files_read


@guarded
def main():
    if not LAKE_DIR.exists():
        fail(f"no lake at {LAKE_DIR} -- task 04 (partitioned-datasets) must be built first")

    gt = load_ground_truth()
    fp = gt["filter_probe"]

    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")

    probe_sql = load_query("probe.sql")
    pruning_sql = load_query("pruning_proof.sql")

    print("running probe.sql via DuckDB ...")
    duckdb_probe = run_probe_duckdb(con, probe_sql)

    print("running the naive pyarrow full-scan baseline ...")
    naive_probe = run_probe_naive(gt)

    print("running pruning_proof.sql and parsing its EXPLAIN ANALYZE plan ...")
    files_read = parse_explain_analyze(con, pruning_sql)

    months = covered_months(fp["captured_at_from"], fp["captured_at_to"])
    files_in_probe_months = sum(1 for m in months for _ in (LAKE_DIR / f"month={m}").glob("*.parquet"))
    files_total_lake = sum(1 for _ in LAKE_DIR.glob("month=*/*.parquet"))

    results = {
        "probe": {
            "duckdb": duckdb_probe,
            "naive": naive_probe,
        },
        "pruning": {
            "files_read_by_pruning_proof": files_read,
            "files_in_probe_months_on_disk": files_in_probe_months,
            "files_total_lake_on_disk": files_total_lake,
            "probe_months": months,
        },
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print()
    print(f"{'':<28}{'duckdb':>14}{'naive':>14}")
    print(f"{'wall time (s)':<28}{duckdb_probe['wall_s']:>14.4f}{naive_probe['wall_s']:>14.4f}")
    print(f"{'rows':<28}{duckdb_probe['row_count']:>14}{naive_probe['row_count']:>14}")
    print(f"{'price_sum':<28}{duckdb_probe['price_sum']:>14.2f}{naive_probe['price_sum']:>14.2f}")
    print()
    print(f"files read by pruned query : {files_read}")
    print(f"files physically in {months} : {files_in_probe_months}")
    print(f"files physically in the whole lake : {files_total_lake}")
    print()
    print(f"results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
