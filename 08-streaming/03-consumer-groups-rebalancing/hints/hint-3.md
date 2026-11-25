Rough shape:

```
running = True

def handle_sigterm(signum, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def log_event(conn, event, partitions):
    with conn:
        with conn.cursor() as cur:
            for tp in partitions:
                cur.execute(
                    "INSERT INTO ops.t03_rebalance_log (member_id, event, partition) "
                    "VALUES (%s, %s, %s)",
                    (my_id, event, tp.partition),
                )

def on_assign(consumer, partitions):
    log_event(log_conn, "assign", partitions)
    consumer.assign(partitions)

def on_revoke(consumer, partitions):
    log_event(log_conn, "revoke", partitions)
    consumer.unassign()

consumer = Consumer({
    "bootstrap.servers": kafka_bootstrap(),
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest",
})
consumer.subscribe([TOPIC], on_assign=on_assign, on_revoke=on_revoke)

while running:
    consumer.poll(1.0)   # discard the message/None result; polling is what
                          # lets the client library process group protocol
                          # traffic (heartbeats, rebalance events) at all

consumer.close()
```

Open one Postgres connection up front (`pg_connect()`) and reuse it for
every `log_event` call — don't reconnect per partition. Keep the callback
bodies small: they block the poll loop, and the poll loop is also what's
carrying the group's heartbeats.

One detail worth checking yourself rather than being told: does `on_assign`
fire with the FULL set of partitions this member now owns, or only the ones
that changed? (Answer it by running member A alone and looking at how many
rows land in `ops.t03_rebalance_log` compared to the partition count — that
observation is exactly the kind of thing NOTES.md asks you to record.)
