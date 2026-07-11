Two designs, same as 07/04, applied here to a CDC stream:

**(a) Dedup table keyed on event identity.** Every message has an identity
that's stable across redelivery: `(msg.partition(), msg.offset())` from the
Kafka message itself, or `payload["source"]["lsn"]` from the decoded
Debezium envelope (the WAL position the change came from -- also stable
across redelivery of the same logical change). Pick one, put it under a
PRIMARY KEY or UNIQUE constraint in your own `ops.t06_*` table, and
`INSERT ... ON CONFLICT DO NOTHING` it at the top of the transaction. Check
whether the insert actually happened (`cur.rowcount`, or `... RETURNING` +
`fetchone()`). Only if it did: apply the replica upsert/delete AND
`applied_changes += 1`, in the same transaction as the dedup insert. A
redelivered event finds its identity already present, the insert loses the
conflict, and you skip straight to committing a no-op.

**(b) Offset stored in the mart, in the same transaction as the write.**
Instead of asking "have I seen this exact event before", track "where did I
get to" as mart state instead of Kafka state: upsert
`(topic, partition) -> offset` into your own `ops.t06_*` table in the SAME
transaction as the replica write and the `applied_changes` increment. On
`on_assign`, look up your stored offset per partition and seek there
(`p.offset = stored + 1`) instead of trusting the broker's committed offset.
Because the offset advance and the increment commit atomically, a crash
before that commit replays from the same offset and reapplies the same
delta exactly once; a crash after it never revisits that offset at all.

Either way: the crash hook's placement (after the mart commit, before the
Kafka offset commit) does not change. What changes is what makes replaying
that window safe.
