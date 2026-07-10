Why the crash run (`S07_CRASH_AFTER=70000`) can't cause loss or
duplication downstream, walked through step by step:

1. The processor is partway through a batch, has produced some output
   records to `s07.t08.enriched` (they're in the log, but the
   transaction hasn't committed yet -- physically present, not yet
   marked committed), and `_maybe_crash` hard-exits via `os._exit(1)`.
   `commit_transaction()` never runs. `send_offsets_to_transaction` may
   or may not have run yet, depending on exactly where in the batch you
   put the crash hook -- either way, the transaction as a whole is
   unfinished.
2. The transaction coordinator eventually marks that transaction as
   aborted (either the coordinator's own timeout, or the fencing that
   happens when the restarted process calls `init_transactions()` again
   with the same `transactional.id`). The output records this
   transaction wrote are still bytes in the `s07.t08.enriched` log, but
   they're tagged as belonging to an aborted transaction.
3. A `read_committed` consumer (what the validator's drain uses, and what
   any real downstream consumer of this topic should use) filters out
   records from aborted transactions at the point of delivery -- it never
   returns them to the application, full stop. This is the mechanism
   that makes step 1's partially-written batch invisible: no dedup logic
   needed on the read side, Kafka does it for you.
4. Meanwhile, on the INPUT side: because `send_offsets_to_transaction`
   for that batch's offsets was tied to the same (aborted) transaction,
   the consumer group's committed offset on `s07.t08.price-updates` never
   advanced past the last SUCCESSFULLY committed batch. On restart, the
   new processor instance resumes from that last-committed offset and
   reprocesses the entire aborted batch's input from scratch -- this
   time producing a fresh, uninterrupted transaction that (assuming no
   second crash) commits cleanly.

Net effect: every input event ends up in exactly one committed
transaction's worth of output, and a `read_committed` reader sees each
`seq` exactly once -- neither the leftover bytes from the aborted
transaction (invisible under read_committed) nor a missing input (offset
never advanced past it) breaks that.
