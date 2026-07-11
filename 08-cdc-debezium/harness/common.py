"""Shared helpers for module 08 (CDC / Debezium) validators, generators, and
task scaffolds.

Every validator prints PASSED or `NOT PASSED: <reason>` and exits 0/1; no
tracebacks reach the learner. Run these host-side via `uv run`. Nothing here
requires a live stack at import time — `confluent_kafka`, `psycopg`, and
`requests` are imported lazily inside the functions that actually need them.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = MODULE_ROOT / "data"
GROUND_TRUTH_PATH = DATA_DIR / "ground-truth.json"

SOURCE_DB = "shop"
MART_DB = "mart"
PG_USER = "sandbox"
PG_PASSWORD = "sandbox"
SOURCE_DEFAULT_PORT = 54308
MART_DEFAULT_PORT = 54318

KAFKA_DEFAULT_PORT = 19093
TOPIC_PREFIX = "s08."

CONNECT_DEFAULT_PORT = 8383


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


def _last_line(text):
    """Last non-empty line of a subprocess stream or HTTP trace -- enough to
    say WHY a run failed without leaking a full traceback/stack dump."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


# --------------------------------------------------------------------------
# Postgres — source (CDC-captured OLTP) and mart (downstream replica)
# --------------------------------------------------------------------------

def _pg_host():
    return os.environ.get("PGHOST", "localhost")


def source_port():
    return int(os.environ.get("SANDBOX_08_SOURCE_PORT", str(SOURCE_DEFAULT_PORT)))


def mart_port():
    return int(os.environ.get("SANDBOX_08_MART_PORT", str(MART_DEFAULT_PORT)))


def source_conninfo():
    return (
        f"host={_pg_host()} port={source_port()} dbname={SOURCE_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def mart_conninfo():
    return (
        f"host={_pg_host()} port={mart_port()} dbname={MART_DB} "
        f"user={PG_USER} password={PG_PASSWORD}"
    )


def source_connect():
    """Live psycopg (v3) connection to the source Postgres, or NOT PASSED."""
    import psycopg

    try:
        return psycopg.connect(source_conninfo())
    except psycopg.Error as e:
        not_passed(f"could not connect to source Postgres on port {source_port()}: {e}")


def mart_connect():
    """Live psycopg (v3) connection to the mart Postgres, or NOT PASSED."""
    import psycopg

    try:
        return psycopg.connect(mart_conninfo())
    except psycopg.Error as e:
        not_passed(f"could not connect to mart Postgres on port {mart_port()}: {e}")


# --------------------------------------------------------------------------
# Kafka / redpanda
# --------------------------------------------------------------------------

def kafka_bootstrap():
    port = int(os.environ.get("SANDBOX_08_KAFKA_PORT", str(KAFKA_DEFAULT_PORT)))
    return f"localhost:{port}"


def admin_client():
    from confluent_kafka.admin import AdminClient

    return AdminClient({"bootstrap.servers": kafka_bootstrap()})


def create_topic(name, partitions=6, cleanup_policy="delete", extra_config=None):
    """Create a topic if it does not already exist (idempotent)."""
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
        "group.id": f"s08-endoffsets-{uuid.uuid4()}",
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
    """dict partition -> committed offset for a consumer group. Partitions
    with no stored commit map to -1 (OFFSET_INVALID)."""
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
    """Delete every module topic (name starting with prefix) for a clean
    slate. Returns the list of topics deleted."""
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


def drain(topic, group=None, timeout=10.0, max_messages=None, from_beginning=True):
    """Consume a topic into a list of raw (key, value) byte-pairs. Side-effect
    free: auto-commit is off and, unless the caller passes a group, an
    ephemeral group is used. Stops after `timeout` seconds elapse with no new
    message, or once `max_messages` have been read. Use decode_value() on the
    returned values to unwrap Debezium's JsonConverter envelope."""
    from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING

    conf = {
        "bootstrap.servers": kafka_bootstrap(),
        "group.id": group or f"s08-drain-{uuid.uuid4()}",
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
            out.append((msg.key(), msg.value()))
            if max_messages is not None and len(out) >= max_messages:
                break
        return out
    finally:
        consumer.close()


# --------------------------------------------------------------------------
# Debezium envelope decoding
# --------------------------------------------------------------------------

def decode_value(raw_bytes):
    """Decode one Kafka message value produced by the Debezium Postgres
    connector. Handles both schemas-enabled (`{"schema": ..., "payload": ...}`
    JsonConverter envelopes, our default -- see docker-compose.yml) and
    schemas-disabled (bare payload dict) converter settings, so consumers
    written against this helper work either way. A tombstone record (value is
    None, published after a delete when tombstones.on.delete=true, the
    Debezium default) decodes to None."""
    if raw_bytes is None:
        return None
    text = raw_bytes.decode("utf-8") if isinstance(raw_bytes, (bytes, bytearray)) else raw_bytes
    obj = json.loads(text)
    if isinstance(obj, dict) and "payload" in obj and "schema" in obj:
        return obj["payload"]
    return obj


def change_op(payload):
    """Given a decoded Debezium payload dict, return (op, before, after):
    op is 'c' (create/insert), 'u' (update), 'd' (delete), 'r' (read, i.e.
    snapshot), or None for a tombstone (payload is None). before/after are
    dicts or None depending on op (e.g. before is None for 'c' and 'r';
    after is None for 'd')."""
    if payload is None:
        return (None, None, None)
    return (payload.get("op"), payload.get("before"), payload.get("after"))


# --------------------------------------------------------------------------
# Kafka Connect REST (Debezium connector lifecycle)
# --------------------------------------------------------------------------

def connect_port():
    return int(os.environ.get("SANDBOX_08_CONNECT_PORT", str(CONNECT_DEFAULT_PORT)))


def connect_url():
    return f"http://localhost:{connect_port()}"


def register_connector(connector_def):
    """Create or update a connector. `connector_def` is shaped like
    {"name": ..., "config": {...}} (e.g. the output of
    debezium_pg_connector_config()). Uses PUT /connectors/<name>/config,
    which is idempotent -- safe to call again with the same or changed
    config."""
    import requests

    name = connector_def["name"]
    url = f"{connect_url()}/connectors/{name}/config"
    try:
        resp = requests.put(url, json=connector_def["config"], timeout=15)
    except requests.RequestException as e:
        not_passed(f"could not reach Kafka Connect at {connect_url()}: {e}")
    if resp.status_code not in (200, 201):
        not_passed(f"failed to register connector {name}: {resp.status_code} {_last_line(resp.text)}")
    return resp.json()


def connector_status(name):
    """GET /connectors/<name>/status, or None if the connector doesn't exist."""
    import requests

    resp = requests.get(f"{connect_url()}/connectors/{name}/status", timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def wait_for_connector_running(name, timeout=60):
    """Poll connector status until the connector and every task report
    RUNNING, or NOT PASSED on timeout / FAILED state. Returns the final
    status dict."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        status = connector_status(name)
        if status is not None:
            last = status
            conn_state = status.get("connector", {}).get("state")
            tasks = status.get("tasks", [])
            failed = [t for t in tasks if t.get("state") == "FAILED"]
            if failed:
                not_passed(f"connector {name} task failed: {_last_line(failed[0].get('trace', ''))}")
            if conn_state == "FAILED":
                not_passed(f"connector {name} failed: {_last_line(status.get('connector', {}).get('trace', ''))}")
            if conn_state == "RUNNING" and tasks and all(t.get("state") == "RUNNING" for t in tasks):
                return status
        time.sleep(2)
    not_passed(f"connector {name} did not reach RUNNING within {timeout}s (last status: {last})")


def delete_connector(name):
    """Delete a connector; ignore the case where it does not exist.

    Also resets the connector's Kafka Connect framework-managed source
    offsets before deleting it. Without this, Kafka Connect's internal
    offsets topic (`s08-connect-offsets`) keeps the last committed offset
    for this connector's source partition (keyed by topic.prefix, which is
    fixed per task -- e.g. "s08.t03") even after the connector and its
    replication slot are gone. Verified live: re-registering a connector
    under the same name/topic.prefix without this reset makes Debezium log
    "A previous offset indicating a completed snapshot has been found" and
    SKIP the snapshot phase entirely on the next run -- against a brand new
    replication slot with zero rows read, so any per-task validator that
    deletes and re-registers its connector (every validator does, on every
    run) would see 0 op=r events on a second run and wrongly fail. The fix:
    PUT /connectors/<name>/stop (required -- offsets can only be reset on a
    STOPPED connector), then DELETE /connectors/<name>/offsets, THEN delete
    the connector itself.
    """
    import requests

    status = requests.get(f"{connect_url()}/connectors/{name}/status", timeout=10)
    if status.status_code == 404:
        return False

    stop_resp = requests.put(f"{connect_url()}/connectors/{name}/stop", timeout=15)
    if stop_resp.status_code not in (202, 204, 404):
        stop_resp.raise_for_status()

    if stop_resp.status_code != 404:
        offsets_resp = requests.delete(f"{connect_url()}/connectors/{name}/offsets", timeout=15)
        if offsets_resp.status_code not in (200, 404):
            offsets_resp.raise_for_status()

    resp = requests.delete(f"{connect_url()}/connectors/{name}", timeout=15)
    if resp.status_code not in (204, 404):
        resp.raise_for_status()
    return resp.status_code != 404


def list_connectors():
    import requests

    resp = requests.get(f"{connect_url()}/connectors", timeout=10)
    resp.raise_for_status()
    return resp.json()


def debezium_pg_connector_config(name, topic_prefix, slot_name, publication_name,
                                  table_include_list, extra=None):
    """Baseline Debezium Postgres connector config, for validators/harness
    use. Individual tasks may ask the learner to write their own config from
    scratch -- this exists so validators and throwaway probe connectors don't
    have to duplicate the boilerplate, not as a learner shortcut.

    table_include_list is a comma-separated "schema.table" string, e.g.
    "shop.offers,shop.products".
    """
    config = {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "plugin.name": "pgoutput",
        "database.hostname": "source",
        "database.port": "5432",
        "database.user": PG_USER,
        "database.password": PG_PASSWORD,
        "database.dbname": SOURCE_DB,
        "topic.prefix": topic_prefix,
        "slot.name": slot_name,
        "publication.name": publication_name,
        "publication.autocreate.mode": "filtered",
        "table.include.list": table_include_list,
        "snapshot.mode": "initial",
        "tombstones.on.delete": "true",
    }
    if extra:
        config.update(extra)
    return {"name": name, "config": config}


# --------------------------------------------------------------------------
# CDC / replication introspection on the SOURCE
# --------------------------------------------------------------------------

def source_current_lsn(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_current_wal_lsn()")
        return cur.fetchone()[0]


def replication_slots(conn):
    """List active/inactive replication slots with lag in bytes
    (pg_current_wal_lsn - restart_lsn). An inactive slot with growing lag is
    a stuck consumer pinning WAL on disk."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT slot_name, active, restart_lsn, confirmed_flush_lsn,
                   pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) AS lag_bytes
            FROM pg_replication_slots
        """)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def drop_slot(conn, name):
    """Drop a replication slot if it exists; no-op (returns False) if it
    doesn't. IMPORTANT operational rule: an orphaned inactive slot pins WAL
    on the source forever (Postgres will not recycle WAL segments the slot
    still needs) until disk fills up. Always drop a task's slot when tearing
    down its connector."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_replication_slots WHERE slot_name = %s", (name,))
        if cur.fetchone() is None:
            return False
        cur.execute("SELECT pg_drop_replication_slot(%s)", (name,))
    conn.commit()
    return True


def drop_publication(conn, name):
    """Drop a publication if it exists; no-op (returns False) if it doesn't."""
    from psycopg import sql

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_publication WHERE pubname = %s", (name,))
        if cur.fetchone() is None:
            return False
        cur.execute(sql.SQL("DROP PUBLICATION {}").format(sql.Identifier(name)))
    conn.commit()
    return True


# --------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------

def load_ground_truth():
    if not GROUND_TRUTH_PATH.exists():
        not_passed(f"ground truth not found at {GROUND_TRUTH_PATH} — run `uv run python generate.py` first")
    return json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
