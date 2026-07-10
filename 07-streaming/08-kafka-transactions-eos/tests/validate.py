"""Validator for 07-streaming task 08 -- kafka-transactions-eos.

Produces the FULL corpus onto s07.t08.price-updates, drives the learner's
processor through ONE injected mid-transaction crash and a final clean
run to completion, then drains s07.t08.enriched with an explicit
read_committed consumer. Checks that the set of `seq` values read
downstream equals exactly {0, ..., total_events - 1} -- proving the
crash-induced aborted transaction lost nothing and leaked nothing.

Run from this task's directory:

    uv run python tests/validate.py
"""

import os
import subprocess
import sys
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = TASK_ROOT.parent
sys.path.insert(0, str(MODULE_ROOT))

from harness.common import (  # noqa: E402
    create_topic,
    guarded,
    iter_events,
    kafka_bootstrap,
    load_ground_truth,
    not_passed,
    passed,
    produce_events,
    reset_topics,
)

INPUT_TOPIC = "s07.t08.price-updates"
OUTPUT_TOPIC = "s07.t08.enriched"
PROCESSOR_SCRIPT = TASK_ROOT / "src" / "processor.py"
CRASH_AFTER = 70000
CRASH_RUN_TIMEOUT = 300
FULL_RUN_TIMEOUT = 300
DRAIN_IDLE_TIMEOUT = 60.0


def _run_processor(env_overrides, timeout):
    env = os.environ.copy()
    env.pop("S07_CRASH_AFTER", None)
    env.update(env_overrides)
    try:
        return subprocess.run(
            ["uv", "run", "python", str(PROCESSOR_SCRIPT)],
            cwd=str(TASK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        not_passed("uv not found on PATH")
    except subprocess.TimeoutExpired:
        return None


def _drain_read_committed(topic, idle_timeout):
    """Drain a topic with an explicit read_committed consumer, from the
    beginning of every partition, until idle. This is the read that
    proves exactly-once: read_committed never surfaces records from an
    aborted transaction, no matter what was physically written to the
    log before a crash."""
    import json
    import uuid

    from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING
    from confluent_kafka.admin import AdminClient

    admin = AdminClient({"bootstrap.servers": kafka_bootstrap()})
    md = admin.list_topics(topic=topic, timeout=10)
    meta = md.topics.get(topic)
    if meta is None or meta.error is not None:
        return []
    partitions = sorted(meta.partitions.keys())
    if not partitions:
        return []

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": f"s07-t08-drain-{uuid.uuid4()}",
        "enable.auto.commit": False,
        "isolation.level": "read_committed",
    })
    try:
        consumer.assign([TopicPartition(topic, p, OFFSET_BEGINNING) for p in partitions])
        out = []
        idle = 0.0
        step = 1.0
        while idle < idle_timeout:
            msg = consumer.poll(step)
            if msg is None:
                idle += step
                continue
            if msg.error():
                idle += step
                continue
            idle = 0.0
            out.append(json.loads(msg.value().decode()))
        return out
    finally:
        consumer.close()


@guarded
def main():
    if not PROCESSOR_SCRIPT.exists():
        not_passed(f"src/processor.py not found at {PROCESSOR_SCRIPT}")

    gt = load_ground_truth()
    total_events = gt["total_events"]

    reset_topics("s07.t08.")
    create_topic(INPUT_TOPIC, partitions=6)
    create_topic(OUTPUT_TOPIC, partitions=6)

    corpus = list(iter_events())
    if len(corpus) != total_events:
        not_passed(
            f"data/events.ndjson has {len(corpus)} lines, ground truth total_events is "
            f"{total_events} -- regenerate the corpus first"
        )

    produced = produce_events(INPUT_TOPIC, corpus, key_field="product_id")
    if produced != total_events:
        not_passed(f"produced {produced} events to {INPUT_TOPIC}, expected {total_events}")

    # --- crash run: kill mid-transaction. Nonzero exit expected and tolerated.
    r1 = _run_processor({"S07_CRASH_AFTER": str(CRASH_AFTER)}, CRASH_RUN_TIMEOUT)
    if r1 is None:
        not_passed(
            f"crash run (S07_CRASH_AFTER={CRASH_AFTER}) did not exit within "
            f"{CRASH_RUN_TIMEOUT}s -- the crash hook should hard-exit almost immediately "
            "once it reaches the count"
        )
    if r1.returncode == 0:
        tail = (r1.stdout or "")[-1000:] + (r1.stderr or "")[-1000:]
        not_passed(
            f"crash run (S07_CRASH_AFTER={CRASH_AFTER}) exited 0 -- expected a nonzero exit "
            f"from the injected os._exit(1) crash hook; is the processor calling "
            f"_maybe_crash from inside an open transaction? output tail:\n{tail}"
        )

    # --- clean run: no crash env, must catch up and exit 0.
    r2 = _run_processor({}, FULL_RUN_TIMEOUT)
    if r2 is None:
        not_passed(
            f"final clean run did not exit within {FULL_RUN_TIMEOUT}s -- did it fail to reach "
            "idle-exit and catch up with the topic?"
        )
    if r2.returncode != 0:
        tail = (r2.stdout or "")[-1500:] + (r2.stderr or "")[-1500:]
        not_passed(f"final clean run exited {r2.returncode} -- output tail:\n{tail}")

    records = _drain_read_committed(OUTPUT_TOPIC, DRAIN_IDLE_TIMEOUT)

    if not records:
        not_passed(
            f"{OUTPUT_TOPIC} is empty under a read_committed drain after both runs -- did "
            "the processor ever commit a transaction? (init_transactions/begin_transaction/"
            "send_offsets_to_transaction/commit_transaction)"
        )

    seqs = [r.get("seq") for r in records]
    if any(s is None for s in seqs):
        not_passed(f"{OUTPUT_TOPIC} has a record missing the 'seq' field")

    seq_set = set(seqs)
    expected_set = set(range(total_events))

    if len(seqs) != len(seq_set):
        dup_count = len(seqs) - len(seq_set)
        not_passed(
            f"{OUTPUT_TOPIC} has {dup_count} duplicate seq value(s) under read_committed -- "
            "aborted-transaction records leaked / committed twice. Check that "
            "send_offsets_to_transaction ties the consumed offsets to the SAME transaction "
            "as the produced records, and that this drain (and any downstream reader) really "
            "uses isolation.level=read_committed"
        )

    missing = expected_set - seq_set
    if missing:
        sample = sorted(missing)[:10]
        not_passed(
            f"{OUTPUT_TOPIC} is missing {len(missing)} seq value(s), e.g. {sample} -- input "
            "events were lost across the crash. Check that send_offsets_to_transaction is "
            "called with the consumer's positions BEFORE commit_transaction, and that the "
            "crashed batch's input offsets never advanced (so it got reprocessed on restart)"
        )

    extra = seq_set - expected_set
    if extra:
        sample = sorted(extra)[:10]
        not_passed(f"{OUTPUT_TOPIC} has unexpected seq value(s) outside range, e.g. {sample}")

    if len(records) != total_events:
        not_passed(
            f"read {len(records)} records from {OUTPUT_TOPIC}, expected exactly {total_events}"
        )

    # Spot-check the derived field on a few records.
    by_seq = {r["seq"]: r for r in records}
    corpus_by_seq = {e["seq"]: e for e in corpus}
    sample_seqs = sorted(by_seq.keys())[:5] + sorted(by_seq.keys())[-5:]
    for s in sample_seqs:
        record = by_seq[s]
        source = corpus_by_seq.get(s)
        if source is None:
            continue
        expected_cents = round(source["price"] * 100)
        if "price_cents" not in record:
            not_passed(f"record for seq={s} is missing a derived field (e.g. price_cents)")
        if abs(record["price_cents"] - expected_cents) > 1:
            not_passed(
                f"record for seq={s} has price_cents={record['price_cents']}, expected "
                f"~{expected_cents}"
            )

    passed(
        f"read_committed drain of {OUTPUT_TOPIC} after an injected mid-transaction crash at "
        f"{CRASH_AFTER} messages: {len(records)} records, seq set exactly matches "
        f"{{0..{total_events - 1}}} (no loss, no duplicates)"
    )


if __name__ == "__main__":
    main()
