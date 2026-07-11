"""Validator for 09-olap-clickhouse-duckdb task 03 -- replacingmergetree-dedup.

Builds a deterministic duplicate-observation batch with
`generate.build_duplicate_batch(SEED, N)` (pure numpy, no DB, no dependency
on the live corpus), computes the expected highest-version survivor for every
natural key in Python, then checks the learner's src/dedup.py:

  1. `create_table` + `insert_batch` land every row (duplicates included) --
     `count_before_merge()` must equal the raw row count.
  2. `count_after_dedup()` must equal the number of DISTINCT natural keys,
     making the collapse visible.
  3. `deduped_state_query()` must return exactly one row per natural key, and
     for EVERY key its version/price/in_stock must match the expected
     highest-version survivor -- proving the read is correct independent of
     whether a background merge has actually run yet.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os

# clickhouse-connect converts naive Python datetimes using the CLIENT
# machine's detected local timezone (not the server's, which is UTC here).
# Fixing TZ=UTC before clickhouse_connect is first imported makes that
# conversion a no-op, so the scraped_at/ingested_at values this validator
# builds compare equal, byte-for-byte, to what comes back out of ClickHouse.
os.environ.setdefault("TZ", "UTC")

import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    ch_client,
    ch_command,
    ch_query,
    guarded,
    not_passed,
    passed,
)
from generate import build_duplicate_batch  # noqa: E402
from src.dedup import (  # noqa: E402
    TABLE,
    count_after_dedup,
    count_before_merge,
    create_table,
    deduped_state_query,
    insert_batch,
)

SEED = 903
N_ROWS = 6000
PRICE_TOL = 1e-6


def _expected_survivors(rows):
    """Group rows by natural key, keep the highest-version row per key."""
    best = {}
    for r in rows:
        key = (r["product_id"], r["seller_id"], r["scraped_at"])
        cur = best.get(key)
        if cur is None or r["version"] > cur["version"]:
            best[key] = r
    return best


def _drop_leftovers(client):
    ch_command(f"DROP TABLE IF EXISTS {TABLE}", client=client)


@guarded
def main():
    rows = build_duplicate_batch(SEED, N_ROWS)
    expected = _expected_survivors(rows)

    client = ch_client()
    try:
        _drop_leftovers(client)

        create_table(client)
        insert_batch(client, rows)

        # 1. Raw row count -- nothing dropped or collapsed at insert time.
        raw_rows = ch_query(count_before_merge(), client=client)
        if not raw_rows or raw_rows[0][0] is None:
            not_passed("count_before_merge() returned no result")
        raw_count = int(raw_rows[0][0])
        if raw_count != len(rows):
            not_passed(
                f"count_before_merge() returned {raw_count}, expected {len(rows)} "
                "(every inserted row, duplicates included)"
            )

        # 2. Deduped distinct-key count.
        dedup_rows = ch_query(count_after_dedup(), client=client)
        if not dedup_rows or dedup_rows[0][0] is None:
            not_passed("count_after_dedup() returned no result")
        dedup_count = int(dedup_rows[0][0])
        if dedup_count != len(expected):
            not_passed(
                f"count_after_dedup() returned {dedup_count}, expected "
                f"{len(expected)} distinct natural keys"
            )

        # 3. The actual current-state read -- must be correct per key,
        #    independent of merge timing.
        state_rows = ch_query(deduped_state_query(), client=client)
        if len(state_rows) != len(expected):
            not_passed(
                f"deduped_state_query() returned {len(state_rows)} rows, expected "
                f"{len(expected)} (exactly one row per natural key)"
            )

        seen = set()
        for row in state_rows:
            if len(row) != 6:
                not_passed(
                    "deduped_state_query() rows must have exactly 6 columns "
                    "(product_id, seller_id, scraped_at, price, in_stock, version), "
                    f"got {len(row)}"
                )
            product_id, seller_id, scraped_at, price, in_stock, version = row
            key = (int(product_id), int(seller_id), scraped_at)
            exp = expected.get(key)
            if exp is None:
                not_passed(f"deduped_state_query() returned an unexpected key {key}")
            seen.add(key)

            if int(version) != exp["version"]:
                not_passed(
                    f"key {key}: version={version}, expected {exp['version']} "
                    "(the highest-version survivor) -- read is not merge-independent"
                )
            if abs(float(price) - exp["price"]) > PRICE_TOL:
                not_passed(
                    f"key {key}: price={price}, expected {exp['price']} "
                    "(the survivor's price)"
                )
            if int(bool(in_stock)) != int(exp["in_stock"]):
                not_passed(
                    f"key {key}: in_stock={in_stock}, expected {int(exp['in_stock'])} "
                    "(the survivor's in_stock)"
                )

        missing = set(expected) - seen
        if missing:
            sample = next(iter(missing))
            not_passed(
                f"deduped_state_query() is missing {len(missing)} natural keys, "
                f"e.g. {sample}"
            )

        passed(
            f"{raw_count} raw rows ({len(rows)} inserted) collapsed to "
            f"{dedup_count} distinct keys; deduped_state_query() correct for all "
            f"{len(expected)} keys"
        )
    finally:
        try:
            _drop_leftovers(client)
        finally:
            client.close()


if __name__ == "__main__":
    main()
