"""Validator for 03-duckdb-cli-swiss-knife. Run from the module root:

    cd toolkit/t3-cli-data-toolkit
    uv run python 03-duckdb-cli-swiss-knife/tests/validate.py

Runs src/solve.sh, parses its three ===Qn=== JSON blocks (each the output
of a `duckdb -json -c ...` call), and compares each against an independent
recomputation done here with pandas directly over the Parquet dir + CSV --
never by re-running the learner's own SQL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
MODULE_ROOT = TASK_DIR.parent
sys.path.insert(0, str(MODULE_ROOT))

import pandas as pd  # noqa: E402

from harness.common import (  # noqa: E402
    check_close,
    guarded,
    not_passed,
    parse_marker_sections,
    passed,
    require_data,
    run_script,
)

LABELS = ["Q1", "Q2", "Q3"]


def _load_frames():
    parquet_dir = require_data("warehouse", "parquet")
    products_csv = require_data("warehouse", "products.csv")
    obs = pd.read_parquet(parquet_dir)
    products = pd.read_csv(products_csv)
    return obs, products


def _expected_q1(obs: pd.DataFrame) -> dict:
    g = obs.groupby("category")["price"].agg(["count", "mean"])
    return {cat: {"obs_count": int(row["count"]), "avg_price": float(row["mean"])} for cat, row in g.iterrows()}


def _expected_q2(obs: pd.DataFrame, products: pd.DataFrame) -> dict:
    merged = obs.merge(products[["product_id", "region"]], on="product_id", how="inner")
    g = merged.groupby("region")["price"].agg(["count", "mean"])
    return {reg: {"obs_count": int(row["count"]), "avg_price": float(row["mean"])} for reg, row in g.iterrows()}


def _expected_q3(obs: pd.DataFrame) -> dict:
    df = obs.sort_values(["product_id", "ts"]).copy()
    df["delta"] = df.groupby("product_id")["price"].diff()
    sub = df.dropna(subset=["delta"])
    out = {}
    for pid, g in sub.groupby("product_id"):
        g = g.sort_values(["delta", "ts"], ascending=[False, True])
        top = g.iloc[0]
        out[pid] = {"jump_ts": str(top["ts"]), "jump_amount": float(top["delta"])}
    return out


def _parse_block(sections: dict, label: str, key_field: str) -> dict:
    text = sections[label].strip()
    if not text:
        not_passed(f"{label}: empty output")
    try:
        rows = json.loads(text)
    except json.JSONDecodeError as e:
        not_passed(f"{label}: not valid JSON: {e}")
    if not isinstance(rows, list):
        not_passed(f"{label}: expected a JSON array, got {type(rows).__name__}")
    by_key = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or key_field not in row:
            not_passed(f"{label}: element {i} is not an object with a '{key_field}' key")
        k = row[key_field]
        if k in by_key:
            not_passed(f"{label}: '{key_field}' value '{k}' appears more than once")
        by_key[k] = row
    return by_key


def _check_agg_block(label: str, actual_by_key: dict, expected_by_key: dict, key_field: str) -> None:
    missing = set(expected_by_key) - set(actual_by_key)
    extra = set(actual_by_key) - set(expected_by_key)
    if missing:
        not_passed(f"{label}: missing {key_field}(s): {sorted(missing)}")
    if extra:
        not_passed(f"{label}: unexpected {key_field}(s): {sorted(extra)}")
    for k, exp in expected_by_key.items():
        row = actual_by_key[k]
        if "obs_count" not in row:
            not_passed(f"{label} ({k}): missing 'obs_count'")
        if row["obs_count"] != exp["obs_count"]:
            not_passed(f"{label} ({k}): obs_count got {row['obs_count']}, expected {exp['obs_count']}")
        if "avg_price" not in row:
            not_passed(f"{label} ({k}): missing 'avg_price'")
        check_close(row["avg_price"], exp["avg_price"], rel_tol=1e-6, label=f"{label} ({k}) avg_price")


@guarded
def main() -> None:
    obs, products = _load_frames()

    expected_q1 = _expected_q1(obs)
    expected_q2 = _expected_q2(obs, products)
    expected_q3 = _expected_q3(obs)

    result = run_script(TASK_DIR / "src" / "solve.sh")
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = tail[-1] if tail else "(no output)"
        not_passed(f"src/solve.sh exited {result.returncode}: {tail}")

    sections = parse_marker_sections(result.stdout, LABELS)

    actual_q1 = _parse_block(sections, "Q1", "category")
    _check_agg_block("Q1", actual_q1, expected_q1, "category")

    actual_q2 = _parse_block(sections, "Q2", "region")
    _check_agg_block("Q2", actual_q2, expected_q2, "region")

    actual_q3 = _parse_block(sections, "Q3", "product_id")
    missing = set(expected_q3) - set(actual_q3)
    extra = set(actual_q3) - set(expected_q3)
    if missing:
        not_passed(f"Q3: missing product_id(s): {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")
    if extra:
        not_passed(f"Q3: unexpected product_id(s): {sorted(extra)[:5]}{'...' if len(extra) > 5 else ''}")
    for pid, exp in expected_q3.items():
        row = actual_q3[pid]
        if row.get("jump_ts") != exp["jump_ts"]:
            not_passed(f"Q3 ({pid}): jump_ts got {row.get('jump_ts')!r}, expected {exp['jump_ts']!r}")
        if "jump_amount" not in row:
            not_passed(f"Q3 ({pid}): missing 'jump_amount'")
        check_close(row["jump_amount"], exp["jump_amount"], rel_tol=1e-6, abs_tol=1e-4, label=f"Q3 ({pid}) jump_amount")

    passed(f"{len(expected_q1)} categories, {len(expected_q2)} regions, {len(expected_q3)} products verified")


if __name__ == "__main__":
    main()
