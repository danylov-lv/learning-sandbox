`consumer.commit(msg)` (no `asynchronous=False` needed -- synchronous is the
default) commits the offset of the partition `msg` belongs to, set to
`msg.offset() + 1`. Call it once per message, not batched -- at this volume
performance isn't the point, correctness under a crash is.

Where does `_maybe_crash(processed)` belong relative to your write and your
commit? It has to interrupt the process at the exact point you want to
inspect. If you want to see what "commit already happened, write didn't"
looks like, the crash has to land after the commit. If you want to see
"write already happened, commit didn't" -- the graded, at-least-once
outcome -- the crash has to land after the write and before the commit.

Also: `idle_seconds` only resets on an actual message (error or not) --
`msg is None` from `poll()` is the "nothing new" case and is what should
accumulate toward `IDLE_EXIT_SECONDS`. Get this wrong and the consumer
either never exits (validator times out) or exits before it's actually
caught up (distinct seq comes up short for a reason that has nothing to do
with delivery semantics).
