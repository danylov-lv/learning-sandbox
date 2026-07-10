"""Validator for 07-streaming/01-log-vs-queue-and-offsets.

Does not import or call the learner's producer/read_history scripts directly
(other than requiring they were already run to populate the topic). Instead
it independently proves, using harness helpers, that the topic the learner
published behaves like a log: two fresh consumer groups each read the full
history, and a third fresh group can replay it again from the beginning.

Run from this task's directory:

    uv run python tests/validate.py
"""

import re
import sys
import uuid
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    drain,
    end_offsets,
    guarded,
    load_ground_truth,
    not_passed,
    passed,
    topic_exists,
)

TOPIC = "s07.t01.price-updates"

NOTES_MIN_CHARS = 600
NOTES_REQUIRED_TERMS = [
    "offset",
    "ack",
    "consumer group",
    "competing consum",
    "replay",
]


def check_notes():
    notes_path = TASK_ROOT / "NOTES.md"
    if not notes_path.exists():
        not_passed("NOTES.md not found in the task directory")
    text = notes_path.read_text(encoding="utf-8")

    m = re.search(r"## Log vs queue: written comparison\n(.*?)(?=\n## |\Z)", text, flags=re.S)
    if not m:
        not_passed('NOTES.md is missing the "## Log vs queue: written comparison" section')
    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S)
    stripped = body.strip()

    if len(stripped) < NOTES_MIN_CHARS:
        not_passed(
            f'the "## Log vs queue: written comparison" section has {len(stripped)} chars, '
            f"need at least {NOTES_MIN_CHARS} of actual written comparison (template text "
            "removed doesn't count)"
        )

    lowered = stripped.lower()
    for term in NOTES_REQUIRED_TERMS:
        if term not in lowered:
            not_passed(
                f'the "## Log vs queue: written comparison" section must discuss '
                f'"{term}" — not found'
            )


@guarded
def main():
    check_notes()

    gt = load_ground_truth()
    total_events = gt["total_events"]
    expected_distinct_products = gt["distinct_products_with_events"]

    if not topic_exists(TOPIC):
        not_passed(f"topic {TOPIC} does not exist — publish the corpus first (run your producer)")

    offsets = end_offsets(TOPIC)
    published = sum(offsets.values())
    if published == 0:
        not_passed("topic exists but is empty — publish the corpus first (run your producer)")
    if published != total_events:
        not_passed(
            f"topic {TOPIC} has {published} messages across its partitions, "
            f"expected {total_events} (ground truth total_events) — publish the whole corpus, once"
        )

    # --- fan-out: two independent fresh groups each see the whole log ---
    group_a = f"t01-verify-a-{uuid.uuid4()}"
    group_b = f"t01-verify-b-{uuid.uuid4()}"

    drained_a = drain(TOPIC, group=group_a, timeout=20.0, from_beginning=True)
    if len(drained_a) != total_events:
        not_passed(
            f"fresh consumer group A read {len(drained_a)} messages from {TOPIC}, "
            f"expected {total_events} — every independent group should see the full log"
        )

    # Group B's pass also does the keying checks (non-null keys, key -> single
    # partition, distinct product count) so the topic only needs one more full
    # scan instead of two separate ones.
    from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING

    from harness.common import kafka_bootstrap, _partition_ids

    consumer = Consumer(
        {
            "bootstrap.servers": kafka_bootstrap(),
            "group.id": group_b,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    partition_for_product = {}
    distinct_products = set()
    read_b = 0
    key_check_target = 200
    sampled = 0
    try:
        parts = _partition_ids(TOPIC)
        consumer.assign([TopicPartition(TOPIC, p, OFFSET_BEGINNING) for p in parts])
        idle = 0.0
        while idle < 20.0:
            msg = consumer.poll(1.0)
            if msg is None:
                idle += 1.0
                continue
            if msg.error():
                idle += 1.0
                continue
            idle = 0.0
            read_b += 1
            key = msg.key()
            if sampled < key_check_target:
                if key is None:
                    not_passed(
                        f"message at partition={msg.partition()} offset={msg.offset()} "
                        "has a null key — key by product_id"
                    )
                sampled += 1
            if key is not None:
                product_id = key.decode()
                distinct_products.add(product_id)
                partition_for_product.setdefault(product_id, set()).add(msg.partition())
    finally:
        consumer.close()

    if read_b != total_events:
        not_passed(
            f"fresh consumer group B read {read_b} messages from {TOPIC}, "
            f"expected {total_events} (same as group A) — two independent groups must "
            "each read the full log, not compete for messages the way RMQ consumers do"
        )

    if sampled < min(key_check_target, total_events):
        not_passed(
            f"only sampled {sampled} keyed messages before running out of topic data — "
            "expected at least a couple hundred"
        )

    # --- replay: a third fresh group re-reads history from offset 0 ---
    group_c = f"t01-verify-replay-{uuid.uuid4()}"
    drained_c = drain(TOPIC, group=group_c, timeout=20.0, from_beginning=True)
    if len(drained_c) != total_events:
        not_passed(
            f"replay group read {len(drained_c)} messages from {TOPIC}, expected {total_events} "
            "— seeking a fresh group to offset 0 must replay the full history"
        )

    misrouted = {pid: parts for pid, parts in partition_for_product.items() if len(parts) > 1}
    if misrouted:
        example_pid, example_parts = next(iter(misrouted.items()))
        not_passed(
            f"product_id {example_pid} appeared on multiple partitions {sorted(example_parts)} — "
            "messages must be keyed by product_id so Kafka's key-based routing sends every "
            "message for a product to the same partition"
        )

    if len(distinct_products) != expected_distinct_products:
        not_passed(
            f"topic {TOPIC} has {len(distinct_products)} distinct product_id keys, "
            f"expected {expected_distinct_products} (ground truth distinct_products_with_events)"
        )

    passed(
        f"{published} events published to {TOPIC}, {len(offsets)} partitions; "
        f"groups A/B/replay each read {total_events}; keys present and product-routed to a "
        f"single partition each; {len(distinct_products)} distinct products match ground truth"
    )


if __name__ == "__main__":
    main()
