"""Validation harness for module 01-sql-foundations.

Usage:
    uv run python validate.py 04     # validate task 04
    uv run python validate.py all    # validate every task

Executes NN-*/src/query.sql against the sandbox DB, normalizes the result
(canonical row sort, floats rounded to 6 significant digits, dates/timestamps
as ISO strings) and compares it with NN-*/tests/expected.json.

Expected values assume the DEFAULT seed scale (1.0).
"""

import json
import math
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg

MODULE_DIR = Path(__file__).resolve().parent


def connect():
    return psycopg.connect(
        host=os.environ.get("SANDBOX_01_HOST", "localhost"),
        port=int(os.environ.get("SANDBOX_01_PORT", "54301")),
        dbname="sandbox",
        user="sandbox",
        password="sandbox",
    )


def round_sig(x, sig=6):
    if x == 0 or not math.isfinite(x):
        return float(x)
    return float(f"{x:.{sig}g}")


def normalize_value(v):
    if v is None or isinstance(v, bool) or isinstance(v, int):
        return v
    if isinstance(v, Decimal) or isinstance(v, float):
        return round_sig(float(v))
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def normalize_result(columns, rows):
    norm = [[normalize_value(v) for v in row] for row in rows]
    norm.sort(key=lambda r: json.dumps(r, default=str))
    return {"columns": list(columns), "rows": norm}


def strip_sql(text):
    lines = []
    for line in text.splitlines():
        code = line.split("--")[0].strip()
        if code:
            lines.append(code)
    return " ".join(lines)


def run_query(sql):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '600s'")
            cur.execute(sql)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall() if cur.description else []
    return columns, rows


def validate_task(task_dir):
    """Returns (passed: bool, message: str)."""
    query_path = task_dir / "src" / "query.sql"
    expected_path = task_dir / "tests" / "expected.json"
    if not query_path.exists():
        return False, f"missing {query_path.name}"
    if not expected_path.exists():
        return False, "missing tests/expected.json"

    sql_text = query_path.read_text(encoding="utf-8")
    if not strip_sql(sql_text):
        return False, "no query written yet"

    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    try:
        columns, rows = run_query(sql_text)
    except psycopg.Error as e:
        first_line = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        return False, f"query error: {first_line}"

    got = normalize_result(columns, rows)

    if got["columns"] != expected["columns"]:
        return False, (
            f"column mismatch: expected {expected['columns']}, got {got['columns']}"
        )
    if len(got["rows"]) != len(expected["rows"]):
        return False, (
            f"row count mismatch: expected {len(expected['rows'])} rows, "
            f"got {len(got['rows'])}"
        )

    diffs = []
    for i, (er, gr) in enumerate(zip(expected["rows"], got["rows"])):
        if er != gr:
            diffs.append((i, er, gr))
        if len(diffs) >= 3:
            break
    if diffs:
        parts = [f"{len(diffs)}+ differing rows (after canonical sort);"]
        for i, er, gr in diffs:
            parts.append(f" row {i}: expected {er}, got {gr};")
        return False, "".join(parts)
    return True, ""


def find_task_dirs():
    return sorted(
        d for d in MODULE_DIR.iterdir()
        if d.is_dir() and len(d.name) > 3 and d.name[:2].isdigit() and d.name[2] == "-"
    )


def main():
    if len(sys.argv) != 2:
        print("usage: uv run python validate.py <NN|all>")
        return 2

    arg = sys.argv[1]
    if arg == "all":
        dirs = find_task_dirs()
        if not dirs:
            print("no task directories found")
            return 1
        failed = 0
        for d in dirs:
            passed, msg = validate_task(d)
            status = "PASSED" if passed else f"NOT PASSED: {msg}"
            print(f"{d.name}: {status}")
            failed += 0 if passed else 1
        return 1 if failed else 0

    num = arg.zfill(2)
    matches = [d for d in find_task_dirs() if d.name.startswith(num + "-")]
    if not matches:
        print(f"NOT PASSED: no task directory matching '{num}-*'")
        return 1
    passed, msg = validate_task(matches[0])
    print("PASSED" if passed else f"NOT PASSED: {msg}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
