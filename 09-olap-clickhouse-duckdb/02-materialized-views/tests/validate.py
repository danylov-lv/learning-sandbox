"""Validator for 09-olap-clickhouse-duckdb task 02 -- materialized-views.

Drops any leftover t02_* objects, calls the learner's create_pipeline, then
STREAMS the existing observations_raw corpus into t02_landing across several
batches (split by product_id ranges, so every batch touches most (day,
category) keys) -- proving the materialized view accumulates a rollup
incrementally, rather than seeing everything in one shot. Finally runs the
learner's final_rollup_query() and checks the collapsed (day, category) ->
(count, price_sum) result against data/ground-truth.json's daily_category,
key set included.

Run from this task's directory:

    uv run python tests/validate.py
"""

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT / "src"))

from harness.common import (  # noqa: E402
    ch_client,
    ch_command,
    ch_query,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
)

import mv  # noqa: E402

LANDING_TABLE = "t02_landing"
TARGET_TABLE = "t02_daily_category"
MV_NAME = "t02_daily_category_mv"

N_BATCHES = 5
PRICE_SUM_TOLERANCE = 0.01

SOURCE_COLUMNS = (
    "observation_id, product_id, seller_id, category, currency, price, in_stock, scraped_at"
)


def _drop_all_t02(client):
    """Drop every t02_* object this task creates, in dependency order (the
    view depends on the landing table as source and the target as
    destination). Safe to call even if create_pipeline never ran."""
    ch_command(f"DROP VIEW IF EXISTS {MV_NAME}", client=client)
    ch_command(f"DROP TABLE IF EXISTS {TARGET_TABLE}", client=client)
    ch_command(f"DROP TABLE IF EXISTS {LANDING_TABLE}", client=client)


def _stream_corpus(client, n_batches):
    """Insert observations_raw into t02_landing in n_batches separate
    INSERT statements, split by product_id modulo -- so each batch spans
    most categories and days, exercising the materialized view's incremental
    accumulation of the SAME (day, category) keys across multiple inserts
    (not just a single one-shot copy)."""
    total = 0
    for i in range(n_batches):
        client.command(
            f"INSERT INTO {LANDING_TABLE} ({SOURCE_COLUMNS}) "
            f"SELECT {SOURCE_COLUMNS} FROM observations_raw "
            f"WHERE product_id % {n_batches} = {i}"
        )
        total += 1
    return total


def _actual_rollup(client):
    sql = mv.final_rollup_query()
    if not isinstance(sql, str) or not sql.strip():
        not_passed("final_rollup_query() did not return a non-empty SQL string")
    rows = ch_query(sql, client=client)
    result = {}
    for day, category, count, price_sum in rows:
        key = f"{day}|{category}"
        if key in result:
            not_passed(
                f"final_rollup_query() returned more than one row for key {key!r} -- "
                "the partials were not fully collapsed"
            )
        result[key] = {"count": int(count), "price_sum": float(price_sum)}
    return result


@guarded
def main():
    gt = load_ground_truth()
    expected = gt["daily_category"]

    client = ch_client()
    try:
        _drop_all_t02(client)

        mv.create_pipeline(client)

        for name in (LANDING_TABLE, TARGET_TABLE):
            exists = ch_query(
                "EXISTS TABLE {name:Identifier}", params={"name": name}, client=client
            )
            if not exists or not exists[0][0]:
                not_passed(f"create_pipeline() did not create table {name!r}")
        exists_mv = ch_query(
            "EXISTS TABLE {name:Identifier}", params={"name": MV_NAME}, client=client
        )
        if not exists_mv or not exists_mv[0][0]:
            not_passed(f"create_pipeline() did not create materialized view {MV_NAME!r}")

        before = ch_query(f"SELECT count() FROM {LANDING_TABLE}", client=client)[0][0]
        if before != 0:
            not_passed(
                f"{LANDING_TABLE} already had {before} rows right after create_pipeline() -- "
                "expected an empty landing table (no POPULATE, no pre-existing data)"
            )

        _stream_corpus(client, N_BATCHES)

        landed = ch_query(f"SELECT count() FROM {LANDING_TABLE}", client=client)[0][0]
        source_total = ch_query("SELECT count() FROM observations_raw", client=client)[0][0]
        if landed != source_total:
            not_passed(
                f"t02_landing has {landed} rows after streaming, expected {source_total} "
                "(sum of observations_raw) -- the batches did not cover the whole corpus"
            )

        actual = _actual_rollup(client)

        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())
        if actual_keys != expected_keys:
            missing = expected_keys - actual_keys
            extra = actual_keys - expected_keys
            detail = []
            if missing:
                detail.append(f"missing {len(missing)} e.g. {sorted(missing)[:5]}")
            if extra:
                detail.append(f"extra {len(extra)} e.g. {sorted(extra)[:5]}")
            not_passed(f"daily_category key set mismatch: {'; '.join(detail)}")

        for key, exp in expected.items():
            got = actual[key]
            if got["count"] != exp["count"]:
                not_passed(
                    f"key {key!r}: count={got['count']}, expected {exp['count']} exactly"
                )
            if abs(got["price_sum"] - exp["price_sum"]) > PRICE_SUM_TOLERANCE:
                not_passed(
                    f"key {key!r}: price_sum={got['price_sum']}, expected {exp['price_sum']} "
                    f"within {PRICE_SUM_TOLERANCE}"
                )

        passed(
            f"{len(expected)} (day, category) keys matched ground truth exactly "
            f"(count exact, price_sum within {PRICE_SUM_TOLERANCE}) after {N_BATCHES} "
            "incremental insert batches"
        )
    finally:
        try:
            _drop_all_t02(client)
        finally:
            client.close()


if __name__ == "__main__":
    main()
