"""Validator for 09-olap-clickhouse-duckdb task 04 -- ttl-and-lifecycle.

Computes the expected surviving row count LIVE against ClickHouse itself
(SELECT count() FROM observations_raw WHERE scraped_at >= now() - INTERVAL
15 MONTH) instead of trusting a static answer key -- since now() moves every
day, the correct surviving count moves with it. The validator queries the
SAME now()-relative cutoff the learner's table TTL uses, at the same moment
it checks the learner's table, so both sides always agree regardless of
what day this runs.

Drops any leftover t04_* table, calls the learner's create_table_with_ttl
and load_from_raw, then force_ttl, then asserts the surviving count and
oldest surviving row match that live-computed expectation exactly.

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
    not_passed,
    passed,
)

import ttl  # noqa: E402

TABLE = "t04_observations_ttl"
RETENTION_MONTHS = 15


def _drop_t04(client):
    ch_command(f"DROP TABLE IF EXISTS {TABLE}", client=client)


def _expected_survivors_and_total(client):
    total = ch_query("SELECT count() FROM observations_raw", client=client)[0][0]
    expected = ch_query(
        f"SELECT count() FROM observations_raw "
        f"WHERE scraped_at >= now() - INTERVAL {RETENTION_MONTHS} MONTH",
        client=client,
    )[0][0]
    return int(expected), int(total)


def _cutoff(client):
    return ch_query(
        f"SELECT now() - INTERVAL {RETENTION_MONTHS} MONTH", client=client
    )[0][0]


@guarded
def main():
    client = ch_client()
    try:
        expected_survivors, total = _expected_survivors_and_total(client)
        if not (0 < expected_survivors < total):
            not_passed(
                f"live now()-relative expected_survivors={expected_survivors} out of "
                f"total={total} is not a non-trivial split (must be strictly between "
                "0 and total) -- the corpus's date range and the current date have "
                "drifted apart from this task's 15-month-retention assumption; this is "
                "a data/date problem, not something src/ttl.py can fix"
            )

        _drop_t04(client)

        ttl.create_table_with_ttl(client)
        ttl.load_from_raw(client)

        # Lenient pre-force check: a merge COULD fire on insert, so this is
        # informational, not a hard gate. The firm check is post-force.
        before = ch_query(ttl.surviving_count_query(), client=client)[0][0]
        if int(before) != total:
            print(
                f"note: count before force_ttl was {before}, expected {total} -- "
                "a merge apparently already ran on insert; continuing"
            )

        ttl.force_ttl(client)

        survivors = ch_query(ttl.surviving_count_query(), client=client)[0][0]
        survivors = int(survivors)
        if survivors != expected_survivors:
            not_passed(
                f"surviving_count_query() returned {survivors}, expected exactly "
                f"{expected_survivors} (live count of observations_raw rows with "
                f"scraped_at >= now() - INTERVAL {RETENTION_MONTHS} MONTH) -- check "
                "the TTL clause on t04_observations_ttl and that force_ttl actually "
                "applied it"
            )
        if survivors >= total:
            not_passed(
                f"surviving_count_query() returned {survivors}, same as the full "
                f"table ({total}) -- the TTL does not appear to have deleted "
                "anything; check force_ttl actually forces a merge/TTL materialize"
            )

        cutoff = _cutoff(client)
        oldest = ch_query(ttl.oldest_surviving_query(), client=client)[0][0]
        if oldest is not None and oldest < cutoff:
            not_passed(
                f"oldest_surviving_query() returned {oldest}, which is older than "
                f"the cutoff {cutoff} (now() - INTERVAL {RETENTION_MONTHS} MONTH) -- "
                "a row that should have expired is still in the table"
            )

        passed(
            f"TTL retained exactly {survivors} of {total} rows "
            f"({survivors / total:.1%}), all with scraped_at >= {cutoff} "
            f"(now() - INTERVAL {RETENTION_MONTHS} MONTH)"
        )
    finally:
        try:
            _drop_t04(client)
        finally:
            client.close()


if __name__ == "__main__":
    main()
