One workable plan, in words:

1. Build the target schema once (explicit `pyarrow.schema(...)`, matching the task-01 13-column contract — reuse what you learned there).
2. Open five `pyarrow.parquet.ParquetWriter` objects up front, one per variant, each with its own `compression=`/`compression_level=` kwargs, all writing to the same schema.
3. Stream `data/raw/*.jsonl` line by line (or file by file, line by line within each file). Accumulate parsed rows into a batch list until you hit a batch size (e.g. 20k-50k rows), then build one `pyarrow.RecordBatch` (or `Table`) from that batch and call `write_table`/`write_batch` on each of the five open writers with the same batch. This is the one-read-pass-fan-out-to-five-writers design — it reads the JSONL exactly once, at the cost of holding five writer buffers open simultaneously.
4. After the last batch, close all five writers and return the row counts (they'll all be equal, since it's the same rows fanned out five ways).

If you'd rather isolate each variant (simpler to reason about, easier to profile independently, but reads the JSONL five times), do a full loop-per-variant instead — parse, build schema, single writer, close, repeat. Time both mentally before you code: five full JSONL reads vs one read with five writer buffers is exactly the kind of tradeoff this task wants you to notice and write down.

For timing hooks: `tests/bench.py` already wraps your whole `write_all` call in one timer and separately times each variant's `pyarrow.parquet.read_table` afterward — you don't need to instrument anything inside `write_all` itself, just make sure it returns control once every file is fully closed and flushed to disk.
