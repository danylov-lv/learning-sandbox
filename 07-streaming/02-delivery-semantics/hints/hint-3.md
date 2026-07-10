Rough shape of the loop body, once `msg` is a real message (not `None`, no
`msg.error()`):

```
idle_seconds = 0.0
event = json.loads(msg.value())
seq = event["seq"]

<step A>
processed += 1
_maybe_crash(processed)
<step B>
```

`record_seen(conn, seq)` and `consumer.commit(msg)` go into `<step A>` and
`<step B>` -- in the order that means "if the process dies right where
`_maybe_crash` is standing, the message has already been durably recorded,
just not yet acknowledged to the broker as consumed". That's the ordering
that turns a mid-stream crash into a duplicate on redelivery instead of a
silent gap.

On the `poll()` result itself:

```
msg = consumer.poll(POLL_TIMEOUT_SECONDS)
if msg is None:
    idle_seconds += POLL_TIMEOUT_SECONDS
    continue
if msg.error():
    idle_seconds = 0.0
    continue  # topic is still alive, just this poll came back an error
# ... the loop body above ...
```
