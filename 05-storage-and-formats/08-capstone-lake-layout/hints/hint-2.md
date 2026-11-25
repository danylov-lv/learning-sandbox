# Hint 2 — the pipeline shape

Stream the raw JSONL once. Do not read it twice (once for bronze, once for
silver) if you can avoid it — but do not force yourself into a single pass
either if that makes the silver sort impossible to do in bounded memory.
The shape that works for both zones without loading the whole dataset:

1. **Bronze first, one linear pass.** Read raw JSONL in chunks, write it
   straight out as Parquet with whatever light normalization you chose
   (documented in NOTES.md). This zone does not need sorting or
   partitioning — it's the cheap, faithful copy you'd rebuild silver from
   if silver's logic ever changes.

2. **Bucket by month.** Silver needs rows grouped by `captured_at`'s
   month before it can sort and write per partition. You cannot sort the
   whole dataset in memory at 10x scale, but you *can* bucket it: stream
   rows through, and for each row, decide which month it belongs to and
   append it to that month's spot. Two ways to make this bounded-memory:
   either read from bronze in chunks and maintain one open writer per
   month (rows arrive already loosely time-ordered from the generator, so
   the number of simultaneously "hot" months at any point in the stream is
   small), or make two passes over bronze — one to bucket into
   per-month intermediate files, one to sort and finalize each month
   independently. Either way, the key insight is that sorting only ever
   has to happen *within* one month's worth of data at a time, never
   across the whole dataset at once.

3. **One writer per partition, with a rolling cutover.** Within a month,
   once you have that month's rows (or a bounded chunk of them) sorted by
   `(source_id, captured_at)`, write them out with a Parquet writer that
   tracks bytes written so far. When the current file crosses your target
   size, close it and open the next one in the same partition directory.
   This is what keeps file counts and file sizes both bounded as data
   volume grows — you are not deciding "N files per partition" up front,
   you are deciding a target file size and letting the row count follow.

4. **A verification pass that reads only metadata.** After writing,
   confirm row counts and partition coverage by reading Parquet
   footers/row-group statistics, not by re-reading and re-summing every
   row. This is both faster and it's the same technique CP2's gates use to
   check your work — building this habit here pays off immediately.

The manifest you return is just a summary of counters you were already
tracking while writing: rows seen per zone, rows written per zone, files
written per zone.
