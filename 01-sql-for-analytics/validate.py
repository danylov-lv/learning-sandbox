"""Validate SQL against the default seed and task-specific fixtures.

Usage:
    uv run python validate.py 04
    uv run python validate.py all
"""

import json
import os
import sys
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql


MODULE_DIR = Path(__file__).resolve().parent
TEMPORAL_COLUMNS = {
    "month": "date",
    "week_start": "date",
    "captured_at": "timestamp",
    "hour_start": "timestamp",
    "streak_start": "timestamp",
    "streak_end": "timestamp",
}


def connect(dbname="sandbox", *, autocommit=False):
    return psycopg.connect(
        host=os.environ.get("SANDBOX_01_HOST", "localhost"),
        port=int(os.environ.get("SANDBOX_01_PORT", "54301")),
        dbname=dbname,
        user="sandbox",
        password="sandbox",
        autocommit=autocommit,
    )


def normalize_value(value):
    if value is None or type(value) in (int, str, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    raise ValueError(f"unsupported result type: {type(value).__name__}")


def strip_sql(text):
    lines = []
    for line in text.splitlines():
        code = line.split("--")[0].strip()
        if code:
            lines.append(code)
    return " ".join(lines)


def run_query(query, *, dbname="sandbox", fixture=None):
    with connect(dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '600s'")
            if fixture is not None:
                schema = MODULE_DIR / "seed" / "schema.sql"
                cur.execute(schema.read_text(encoding="utf-8"))
                cur.execute(fixture.read_text(encoding="utf-8"))
            cur.execute(query)
            description = cur.description or []
            rows = cur.fetchall() if description else []
            return description, rows


def run_edge_query(query, fixture):
    dbname = f"sandbox_01_check_{uuid4().hex}"
    database = sql.Identifier(dbname)
    with connect(autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(database))
        try:
            return run_query(query, dbname=dbname, fixture=fixture)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(database))


def compare_result(description, rows, expected):
    columns = [column.name for column in description]
    if columns != expected["columns"]:
        return f"column mismatch: expected {expected['columns']}, got {columns}"

    for column in description:
        type_name = TEMPORAL_COLUMNS.get(column.name)
        if type_name and column.type_code != psycopg.adapters.types[type_name].oid:
            return f"column type mismatch: {column.name} must be {type_name}"

    expected_rows = expected["rows"]
    if len(rows) != len(expected_rows):
        return f"row count mismatch: expected {len(expected_rows)} rows, got {len(rows)}"

    try:
        actual = Counter(tuple(normalize_value(value) for value in row) for row in rows)
    except ValueError as exc:
        return str(exc)

    target = Counter(tuple(row) for row in expected_rows)
    if actual == target:
        return ""

    missing = list(islice((target - actual).elements(), 3))
    unexpected = list(islice((actual - target).elements(), 3))
    return f"differing rows (up to 3 shown): expected {missing}, got {unexpected}"


def validate_task(task_dir):
    query_path = task_dir / "src" / "query.sql"
    tests = task_dir / "tests"
    expected_path = tests / "expected.json"
    if not query_path.exists():
        return False, f"missing {query_path.name}"
    if not expected_path.exists():
        return False, "missing tests/expected.json"

    query = query_path.read_text(encoding="utf-8")
    if not strip_sql(query):
        return False, "no query written yet"

    checks = [(None, expected_path)]
    edge_setup = tests / "edge_setup.sql"
    edge_expected = tests / "edge_expected.json"
    if edge_setup.exists() != edge_expected.exists():
        return False, "edge fixture requires edge_setup.sql and edge_expected.json"
    if edge_setup.exists():
        checks.append((edge_setup, edge_expected))

    for fixture, path in checks:
        expected = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        try:
            if fixture is None:
                description, rows = run_query(query)
            else:
                description, rows = run_edge_query(query, fixture)
            mismatch = compare_result(description, rows, expected)
        except psycopg.Error as exc:
            lines = str(exc).strip().splitlines()
            mismatch = f"query error: {lines[0] if lines else type(exc).__name__}"

        if mismatch:
            if fixture is not None:
                mismatch = f"edge fixture: {mismatch}"
            return False, mismatch
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
