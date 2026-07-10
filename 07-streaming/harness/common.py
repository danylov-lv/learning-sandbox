"""Shared helpers for module 07 (streaming) validators and generators.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Nothing here
requires a live broker or Postgres at import time — `confluent_kafka` and
`psycopg` are imported lazily inside the functions that actually need them, so
importing this module never depends on the stack being up.
"""

import json
import os
import sys
import uuid
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
EVENTS_PATH = DATA_DIR / "events.ndjson"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

PG_DB = "streaming"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"
PG_DEFAULT_PORT = 54307

KAFKA_DEFAULT_PORT = 19092
TOPIC_PREFIX = "s07."


def not_passed(reason):
    print(f"NOT PASSED: {reason}")
    sys.exit(1)


def passed(msg=""):
    print(f"PASSED{': ' + msg if msg else ''}")
    sys.exit(0)


def guarded(fn):
    """Decorator: wrap a validator body so unexpected exceptions become
    NOT PASSED instead of a raw traceback."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SystemExit:
            raise
        except NotImplementedError:
            not_passed("scaffold not implemented yet (NotImplementedError)")
        except Exception as e:
            not_passed(f"unexpected error: {type(e).__name__}: {e}")

    return wrapper


# --------------------------------------------------------------------------
# Postgres
# --------------------------------------------------------------------------

def pg_port():
    return int(os.environ.get("SANDBOX_07_PORT", str(PG_DEFAULT_PORT)))


def pg_conninfo():
    host = os.environ.get("PGHOST", "localhost")
    return (
        f"host={host} port={pg_port()} dbname={PG_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def pg_connect():
    """Return a live psycopg (v3) connection, or NOT PASSED if it can't connect."""
    import psycopg

    try:
        return psycopg.connect(pg_conninfo())
    except psycopg.Error as e:
        not_passed(f"could not connect to Postgres on port {pg_port()}: {e}")


# --------------------------------------------------------------------------
# Kafka / redpanda
# --------------------------------------------------------------------------

def kafka_bootstrap():
    port = int(os.environ.get("SANDBOX_07_KAFKA_PORT", str(KAFKA_DEFAULT_PORT)))
    return f"localhost:{port}"


def admin_client():
    from confluent_kafka.admin import AdminClient

    return AdminClient({"bootstrap.servers": kafka_bootstrap()})


def create_topic(name, partitions=6, cleanup_policy="delete", extra_config=None):
    """Create a topic if it does not already exist (idempotent). cleanup_policy
    is "delete" (normal log) or "compact" (compacted, latest-value-per-key)."""
    from confluent_kafka.admin import NewTopic
    from confluent_kafka import KafkaError, KafkaException

    config = {"cleanup.policy": cleanup_policy}
    if extra_config:
        config.update(extra_config)
    topic = NewTopic(name, num_partitions=partitions, replication_factor=1, config=config)
    admin = admin_client()
    fut = admin.create_topics([topic])[name]
    try:
        fut.result()
    except KafkaException as e:
        if e.args[0].code() == KafkaError.TOPIC_ALREADY_EXISTS:
            return False
        raise
    return True


def delete_topic(name):
    """Delete a topic; ignore the case where it does not exist."""
    from confluent_kafka import KafkaError, KafkaException

    admin = admin_client()
    fut = admin.delete_topics([name])[name]
    try:
        fut.result()
    except KafkaException as e:
        if e.args[0].code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
            return False
        raise
    return True


def topic_exists(name):
    md = admin_client().list_topics(timeout=10)
    return name in md.topics


def list_topics():
    """Sorted list of non-internal topic names known to the cluster."""
    md = admin_client().list_topics(timeout=10)
    return sorted(t for t in md.topics if not t.startswith("__"))


def _partition_ids(topic, timeout=10):
    md = admin_client().list_topics(topic=topic, timeout=timeout)
    meta = md.topics.get(topic)
    if meta is None or meta.error is not None:
        return []
    return sorted(meta.partitions.keys())


def end_offsets(topic):
    """dict partition -> high watermark (next offset to be written)."""
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": f"s07-endoffsets-{uuid.uuid4()}",
        "enable.auto.commit": False,
    })
    try:
        out = {}
        for p in _partition_ids(topic):
            _low, high = consumer.get_watermark_offsets(
                TopicPartition(topic, p), timeout=10.0, cached=False
            )
            out[p] = high
        return out
    finally:
        consumer.close()


def committed_offsets(group, topic):
    """dict partition -> committed offset for a consumer group. Partitions with
    no stored commit map to -1 (OFFSET_INVALID)."""
    from confluent_kafka import Consumer, TopicPartition, OFFSET_INVALID

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": group,
        "enable.auto.commit": False,
    })
    try:
        tps = [TopicPartition(topic, p) for p in _partition_ids(topic)]
        if not tps:
            return {}
        committed = consumer.committed(tps, timeout=10.0)
        out = {}
        for tp in committed:
            out[tp.partition] = -1 if tp.offset == OFFSET_INVALID else tp.offset
        return out
    finally:
        consumer.close()


def consumer_lag(group, topic):
    """Total lag = sum over partitions of (high watermark - committed). A
    partition with no committed offset counts its full backlog (high - low)."""
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": group,
        "enable.auto.commit": False,
    })
    try:
        tps = [TopicPartition(topic, p) for p in _partition_ids(topic)]
        if not tps:
            return 0
        committed = {tp.partition: tp.offset for tp in consumer.committed(tps, timeout=10.0)}
        total = 0
        for p in [tp.partition for tp in tps]:
            low, high = consumer.get_watermark_offsets(
                TopicPartition(topic, p), timeout=10.0, cached=False
            )
            c = committed.get(p, -1)
            floor = c if c >= 0 else low
            total += max(0, high - floor)
        return total
    finally:
        consumer.close()


def reset_topics(prefix=TOPIC_PREFIX):
    """Delete every module topic (name starting with prefix) for a clean slate.
    Returns the list of topics deleted."""
    from confluent_kafka import KafkaException

    admin = admin_client()
    md = admin.list_topics(timeout=10)
    targets = [t for t in md.topics if t.startswith(prefix)]
    if not targets:
        return []
    futs = admin.delete_topics(targets, operation_timeout=30)
    deleted = []
    for name, fut in futs.items():
        try:
            fut.result()
            deleted.append(name)
        except KafkaException:
            pass
    return deleted


def produce_events(topic, events, key_field="product_id", transactional=False,
                   transactional_id=None, acks="all"):
    """Produce an iterable of event dicts to a topic. Value = JSON bytes of the
    dict, key = str(event[key_field]).encode(). Flushes before returning. When
    transactional=True, wraps the batch in a single Kafka transaction. Returns
    the count produced."""
    from confluent_kafka import Producer

    conf = {"bootstrap.servers": kafka_bootstrap(), "acks": acks}
    if transactional:
        conf["transactional.id"] = transactional_id or f"s07-producer-{uuid.uuid4()}"
    producer = Producer(conf)

    if transactional:
        producer.init_transactions()
        producer.begin_transaction()

    count = 0
    try:
        for event in events:
            key = str(event[key_field]).encode() if key_field is not None else None
            value = json.dumps(event, ensure_ascii=False).encode()
            producer.produce(topic, value=value, key=key)
            count += 1
            if count % 10000 == 0:
                producer.poll(0)
        producer.flush()
        if transactional:
            producer.commit_transaction()
    except Exception:
        if transactional:
            producer.abort_transaction()
        raise
    return count


def drain(topic, group=None, timeout=10.0, max_messages=None, from_beginning=True):
    """Consume a topic into a list of decoded event dicts. Side-effect free:
    auto-commit is off and, unless the caller passes a group, an ephemeral group
    is used. Stops after `timeout` seconds elapse with no new message, or once
    `max_messages` have been read. from_beginning assigns all partitions and
    seeks to the start regardless of any stored offsets."""
    from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING

    conf = {
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": group or f"s07-drain-{uuid.uuid4()}",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    }
    consumer = Consumer(conf)
    try:
        if from_beginning:
            parts = _partition_ids(topic)
            if not parts:
                return []
            consumer.assign([TopicPartition(topic, p, OFFSET_BEGINNING) for p in parts])
        else:
            consumer.subscribe([topic])

        out = []
        idle = 0.0
        step = 1.0
        while idle < timeout:
            msg = consumer.poll(step)
            if msg is None:
                idle += step
                continue
            if msg.error():
                idle += step
                continue
            idle = 0.0
            out.append(json.loads(msg.value().decode()))
            if max_messages is not None and len(out) >= max_messages:
                break
        return out
    finally:
        consumer.close()


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------

def iter_events():
    """Yield event dicts from data/events.ndjson in file (publish/seq) order."""
    if not EVENTS_PATH.exists():
        not_passed(f"events not found at {EVENTS_PATH} — run `uv run python generate.py` first")
    with EVENTS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
