"""Validator for 10-nosql-patterns task 03 -- dedup-filter.

Checks FOUR independent things about the learner's src/dedup.py:

  1. SetDedup is EXACT -- the number of add_if_new() True results over the
     whole event url stream equals ground-truth's events.unique_urls exactly
     (0 false positives, 0 false negatives).
  2. BloomDedup has NO FALSE NEGATIVES -- after feeding every url once, every
     DISTINCT url fed a second time must report False (not new). A single
     True on the replay is a false negative and fails the task.
  3. BloomDedup's false-positive rate is IN TOLERANCE -- its own count of
     True results on the first pass (its estimate of the unique count) must
     be at or below the true unique count, and not below it by more than a
     small multiple of the configured error_rate.
  4. MEMORY tradeoff -- MEMORY USAGE of the Bloom key must be strictly less
     than MEMORY USAGE of the SET key after both absorbed the same urls.

Run from the 10-nosql-patterns directory:

    uv run python 03-dedup-filter/tests/validate.py
"""

import json
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(TASK_ROOT))

from harness.common import (  # noqa: E402
    EVENTS_PATH,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    redis_client,
    redis_flush_prefix,
)
from src.dedup import BloomDedup, SetDedup  # noqa: E402

PREFIX = "s10:t03:"
SET_KEY = PREFIX + "seen-urls:set"
BLOOM_KEY = PREFIX + "seen-urls:bloom"

ERROR_RATE = 0.01
# The FP-rate check tolerates the Bloom's unique-count estimate falling up to
# k * error_rate below the true count -- a small multiple, so a wildly-off
# implementation fails while normal Bloom noise passes.
FP_TOLERANCE_K = 3


def _load_urls():
    if not EVENTS_PATH.exists():
        not_passed(f"event data not found at {EVENTS_PATH} -- run `uv run python generate.py` first")
    urls = []
    with open(EVENTS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            urls.append(json.loads(line)["url"])
    return urls


@guarded
def main():
    gt = load_ground_truth()
    unique_urls = gt["events"]["unique_urls"]

    client = redis_client()
    redis_flush_prefix(client, PREFIX)

    urls = _load_urls()
    distinct_urls = list(dict.fromkeys(urls))
    if len(distinct_urls) != unique_urls:
        not_passed(
            f"data/events.json has {len(distinct_urls)} distinct urls, "
            f"expected {unique_urls} from ground truth -- data mismatch, "
            "was generate.py rerun at a different SCALE?"
        )

    # 1. SetDedup must be exact.
    set_dedup = SetDedup(client, SET_KEY)
    set_new_count = sum(1 for u in urls if set_dedup.add_if_new(u))
    if set_new_count != unique_urls:
        not_passed(
            f"SetDedup reported {set_new_count} new urls over the stream, "
            f"expected exactly {unique_urls} (SET dedup must be exact)"
        )

    # 2 & 3. BloomDedup: no false negatives, false-positive rate in tolerance.
    bloom_dedup = BloomDedup(client, BLOOM_KEY, capacity=unique_urls, error_rate=ERROR_RATE)
    bloom_dedup.ensure()

    bloom_new_count = sum(1 for u in urls if bloom_dedup.add_if_new(u))

    if bloom_new_count > unique_urls:
        not_passed(
            f"BloomDedup reported {bloom_new_count} new urls, more than the true "
            f"unique count {unique_urls} -- a Bloom filter can only ever "
            "UNDER-count uniques (false positives), never over-count"
        )
    lower_bound = unique_urls * (1 - FP_TOLERANCE_K * ERROR_RATE)
    if bloom_new_count < lower_bound:
        not_passed(
            f"BloomDedup reported {bloom_new_count} new urls out of {unique_urls} "
            f"true uniques -- expected at least {lower_bound:.0f} "
            f"(error_rate={ERROR_RATE}, tolerance k={FP_TOLERANCE_K}); false-positive "
            "rate looks far higher than configured"
        )

    false_negatives = 0
    for u in distinct_urls:
        if bloom_dedup.add_if_new(u):
            false_negatives += 1
    if false_negatives:
        not_passed(
            f"BloomDedup reported {false_negatives} false negative(s) on replay -- "
            "a url already added must NEVER report as new again"
        )

    # 4. Memory tradeoff.
    set_mem = client.memory_usage(SET_KEY)
    bloom_mem = client.memory_usage(BLOOM_KEY)
    if set_mem is None or bloom_mem is None:
        not_passed("MEMORY USAGE returned None for one of the keys -- did ensure()/add_if_new() run?")
    if not (bloom_mem < set_mem):
        not_passed(
            f"Bloom key used {bloom_mem} bytes, SET key used {set_mem} bytes -- "
            "expected the Bloom filter to use strictly less memory"
        )

    passed(
        f"SET exact over {unique_urls} unique urls; Bloom found {bloom_new_count} "
        f"unique ({unique_urls - bloom_new_count} false positives, 0 false negatives "
        f"on replay of {len(distinct_urls)} distinct urls); memory: "
        f"set={set_mem}B bloom={bloom_mem}B ({bloom_mem / set_mem:.1%} of SET)"
    )


if __name__ == "__main__":
    main()
