Start by separating two ideas that Kafka lets you blur together: "reading an
entry" and "being done with an entry." A Redis Stream is a persistent log --
`XADD` appends, entries don't vanish when read. A consumer GROUP layered on
top of a stream additionally tracks, per entry, who it was delivered to and
whether that consumer has said "I'm done" yet. That per-entry, per-consumer
bookkeeping is the Pending Entries List (PEL), and it's a genuinely different
mechanism from a Kafka committed offset (a single number meaning "everything
up to here is done").

Before writing any code, work out which of your five functions only touch the
log (append, or plain history read) and which touch the PEL (delivery,
acknowledgement, reassignment). `produce` is log-only. Everything else in this
task revolves around the PEL. If reading an entry automatically finished it,
there would be nothing to reclaim after a crash -- so ask yourself: what
Redis command reads NEW entries for a group AND leaves them marked
outstanding, and what command is the ONLY way to clear that mark?
