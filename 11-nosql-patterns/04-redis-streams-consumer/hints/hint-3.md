Recovery reads the PEL from the other side: `XPENDING <key> <group>` (no
extra args) gives you a summary -- how many entries are pending, the
lowest/highest pending ID, and a per-consumer breakdown. The extended form,
`XPENDING <key> <group> <min> <max> <count> [consumer]`, lists individual
entries with their consumer name and idle time. That's enough to build
recovery by hand: find entries idle longer than your threshold, then
`XCLAIM <key> <group> <new-consumer> <min-idle-time> <id> [id ...]` to
reassign them.

`XAUTOCLAIM <key> <group> <new-consumer> <min-idle-time> <start>` folds both
steps into one call: give it a starting cursor (`"0-0"` to scan from the
beginning of the PEL) and it scans for entries idle at least
`min-idle-time`, reassigns up to `count` of them to `new-consumer`, and hands
them back already reassigned -- same `(id, fields)` shape XREADGROUP gives
you, ready to process. It scans across ALL consumers' pending entries, not
just one -- which is the point: the consumer that's actually still alive
doesn't need to know the name of the one that died, it just needs "anything
stuck long enough is up for grabs."

Contrast this with Kafka: there, recovering a dead consumer's work means the
GROUP COORDINATOR reassigns that consumer's whole PARTITION to someone else
during a rebalance, and the new owner resumes from the last committed
offset -- an all-or-nothing handoff at partition granularity, which can
redeliver entries the dead consumer had actually finished but not yet
committed. `XAUTOCLAIM`'s unit of recovery is a single entry, chosen by how
long it's actually been sitting unacked -- finer-grained, and it never
touches entries a still-busy, still-alive consumer legitimately holds
(their idle time hasn't crossed your threshold). Either way -- Kafka
redelivering from an offset, or Streams reclaiming a stuck entry -- the
guarantee is at-least-once, not exactly-once: your downstream processing
still needs to be idempotent, because the same entry can genuinely be
processed twice (once by the consumer that died right after finishing but
before acking, once by whoever reclaims it).
