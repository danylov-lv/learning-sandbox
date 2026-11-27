"""Validator for the PriceWatch question battery (q01-q15).

Runs learner-written SQL files against a live Postgres instance and compares
the result set to the reference answers computed by harness/ground_truth.py.

Usage (from module root):
    uv run python harness/validate.py --task 01
    uv run python harness/validate.py --q q05
    uv run python harness/validate.py --q q05,q06
    uv run python harness/validate.py --q q05 --file scratch/q05_try.sql
    uv run python harness/validate.py --all
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
from decimal import Decimal

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import ground_truth  # noqa: E402
import star_schema  # noqa: E402

ALL_QUESTIONS = [
    "q01", "q02", "q03", "q04",
    "q05", "q06", "q07", "q08",
    "q09", "q10", "q11",
    "q12", "q13a", "q13b", "q14", "q15",
]

TASK_QUESTIONS = {
    "01": ["q01", "q02", "q03", "q04"],
    "02": ["q05", "q06", "q07", "q08"],
    "03": ["q09", "q10", "q11"],
    "04": ["q12", "q13a", "q13b", "q14", "q15"],
}

DEFAULT_SQL_PATH = {
    "q01": "01-relational-core/src/q01.sql",
    "q02": "01-relational-core/src/q02.sql",
    "q03": "01-relational-core/src/q03.sql",
    "q04": "01-relational-core/src/q04.sql",
    "q05": "02-scd2-history/src/q05.sql",
    "q06": "02-scd2-history/src/q06.sql",
    "q07": "02-scd2-history/src/q07.sql",
    "q08": "02-scd2-history/src/q08.sql",
    "q09": "03-star-schema/src/q09.sql",
    "q10": "03-star-schema/src/q10.sql",
    "q11": "03-star-schema/src/q11.sql",
    "q12": "04-capstone-bitemporal/src/q12.sql",
    "q13a": "04-capstone-bitemporal/src/q13a.sql",
    "q13b": "04-capstone-bitemporal/src/q13b.sql",
    "q14": "04-capstone-bitemporal/src/q14.sql",
    "q15": "04-capstone-bitemporal/src/q15.sql",
}

def default_dsn():
    port = os.environ.get("SANDBOX_03_PORT", "54303")
    return f"postgresql://sandbox:sandbox@localhost:{port}/sandbox"


def strip_sql_comments(text):
    no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    no_line = re.sub(r"--[^\n]*", "", no_block)
    return no_line


def is_stub(text):
    return strip_sql_comments(text).strip() == ""


def read_sql_file(path):
    if not os.path.exists(path):
        return None, f"{os.path.relpath(path, MODULE_ROOT)} not found -- write your query there"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if is_stub(text):
        return None, f"{os.path.relpath(path, MODULE_ROOT)} is still a stub -- write your query there"
    return text, None


def first_error_line(exc):
    msg = str(exc).strip()
    return msg.splitlines()[0] if msg else repr(exc)


def normalize_value(v, expected_v):
    if v is None:
        return None
    if isinstance(v, (dt.datetime,)):
        d = v
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        else:
            d = d.astimezone(dt.timezone.utc)
        return d.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(v, dt.date):
        return v.strftime("%Y-%m-%d")
    if isinstance(expected_v, float) and isinstance(v, (Decimal, int, float)) and not isinstance(v, bool):
        return round(float(v), 4)
    if isinstance(v, str):
        if isinstance(expected_v, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", expected_v):
            # value came back as text already in timestamp format
            m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", v)
            if m:
                return m.group(1) + "Z"
        return v
    return v


def normalize_row(row, expected_row):
    return [normalize_value(v, ev) for v, ev in zip(row, expected_row)]


def values_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def row_sort_key(row):
    return json.dumps(row, sort_keys=True, default=str)


def compare_rows(got_rows, expected_rows):
    """Returns (ok, reason). got_rows/expected_rows already normalized lists."""
    if len(got_rows) != len(expected_rows):
        reason = f"row count mismatch: got {len(got_rows)}, expected {len(expected_rows)}"
        return False, reason, got_rows, expected_rows

    got_sorted = sorted(got_rows, key=row_sort_key)
    exp_sorted = sorted(expected_rows, key=row_sort_key)

    # Compare row values after normalizing decimal answers to four places.
    remaining = list(range(len(exp_sorted)))
    unmatched_got = []
    for g in got_sorted:
        matched_idx = None
        for i in remaining:
            e = exp_sorted[i]
            if len(g) == len(e) and all(values_equal(gv, ev) for gv, ev in zip(g, e)):
                matched_idx = i
                break
        if matched_idx is None:
            unmatched_got.append(g)
        else:
            remaining.remove(matched_idx)

    if not unmatched_got and not remaining:
        return True, None, [], []

    unmatched_expected = [exp_sorted[i] for i in remaining]
    return False, "row content mismatch", unmatched_got, unmatched_expected


def run_question(qkey, sql_path, expected, conn_kwargs, star_precheck_failed):
    if qkey in star_schema.REPORT_TABLES and star_precheck_failed:
        print(f"NOT PASSED ({qkey}): {star_precheck_failed}")
        return False

    text, err = read_sql_file(sql_path)
    if err:
        print(f"NOT PASSED ({qkey}): {err}")
        return False

    try:
        with psycopg.connect(**conn_kwargs) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {star_schema.STATEMENT_TIMEOUT_MS}")
                if qkey in star_schema.REPORT_TABLES:
                    error = star_schema.prepare_report(cur, qkey, text)
                    if error:
                        print(f"NOT PASSED ({qkey}): {error}")
                        return False
                    cur.execute("SELECT * FROM pg_temp.pricewatch_report")
                else:
                    cur.execute(text)
                got_columns = [d.name for d in cur.description] if cur.description else []
                got_rows_raw = cur.fetchall()
    except Exception as exc:
        print(f"NOT PASSED ({qkey}): {first_error_line(exc)}")
        return False

    expected_columns = expected["columns"]
    if [c.lower() for c in got_columns] != [c.lower() for c in expected_columns]:
        print(f"NOT PASSED ({qkey}): column mismatch -- got {got_columns}, expected {expected_columns}")
        return False

    expected_rows = expected["rows"]
    template = [
        next((value for value in column if value is not None), None)
        for column in zip(*expected_rows)
    ] or [None] * len(got_columns)
    got_rows = [normalize_row(list(r), template) for r in got_rows_raw]

    ok, reason, extra_got, extra_expected = compare_rows(got_rows, expected_rows)
    if not ok:
        print(f"NOT PASSED ({qkey}): {reason}")
        print(f"  got {len(got_rows)} rows, expected {len(expected_rows)} rows")
        if extra_got:
            print(f"  present only in your result (up to 3): {extra_got[:3]}")
        if extra_expected:
            print(f"  present only in expected result (up to 3): {extra_expected[:3]}")
        return False

    print(f"PASSED ({qkey})")
    return True


def main():
    ap = argparse.ArgumentParser(description="Validate PriceWatch learner SQL against ground truth")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", choices=["01", "02", "03", "04"])
    group.add_argument("--q", help="single question key or comma-separated list, e.g. q05 or q05,q06")
    group.add_argument("--all", action="store_true")
    ap.add_argument("--file", help="override SQL file path; only valid with a single --q")
    ap.add_argument("--dsn", default=None)
    args = ap.parse_args()

    if args.task:
        questions = TASK_QUESTIONS[args.task]
    elif args.all:
        questions = ALL_QUESTIONS
    else:
        questions = [q.strip() for q in args.q.split(",") if q.strip()]
        unknown = [q for q in questions if q not in ALL_QUESTIONS]
        if unknown:
            ap.error(f"unknown question key(s): {unknown}; known: {ALL_QUESTIONS}")

    if args.file and (args.task or args.all or len(questions) != 1):
        ap.error("--file is only allowed together with a single --q")

    dsn = args.dsn or default_dsn()
    conn_kwargs = {"conninfo": dsn}

    try:
        gt = ground_truth.load_or_compute()
    except (OSError, ValueError, KeyError, AssertionError) as exc:
        print(f"NOT PASSED: {first_error_line(exc)}")
        sys.exit(1)
    answers = gt["answers"]

    star_precheck_failed = None
    if any(q in star_schema.REPORT_TABLES for q in questions):
        star_precheck_failed = star_schema.check_structure(conn_kwargs, gt["notes"]["dedup_obs"])

    passed = 0
    for qkey in questions:
        if args.file:
            sql_path = os.path.normpath(os.path.join(MODULE_ROOT, args.file))
        else:
            sql_path = os.path.join(MODULE_ROOT, DEFAULT_SQL_PATH[qkey])
        expected = answers[qkey]
        ok = run_question(qkey, sql_path, expected, conn_kwargs, star_precheck_failed)
        if ok:
            passed += 1

    total = len(questions)
    print(f"{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
