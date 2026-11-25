# Hint 3

A concrete shape for both converters, in words (no code):

**Parquet**

1. Define the output schema once, up front: 13 fields in the contract's
   order, with the contract's types — including a timestamp field with
   microsecond (or nanosecond) resolution and `tz="UTC"`.
2. Open a Parquet writer against `out_path` with that schema.
3. Iterate the `part-*.jsonl` files in order; within each file, read lines
   in fixed-size batches (e.g. a few tens of thousands of lines per batch —
   big enough to be efficient, small enough to stay well under a few
   hundred MB per batch).
4. For each batch: `json.loads` every line, then build one column at a
   time as a plain Python list (or a numpy array where it helps) —
   `product_id`, `source_id`, ..., `price` (with `None` staying `None`),
   ..., `captured_at` (parse each ISO string into an aware UTC `datetime`),
   `attrs` (re-`json.dumps` the dict back to a string), etc.
5. Wrap those columns into a `pa.RecordBatch` built against the schema from
   step 1 (this is where type mismatches get caught — a wrong Python type
   in a column will raise at construction time, which is a feature, not a
   bug).
6. Write the batch to the writer, discard it, move to the next batch.
7. Close the writer when input is exhausted; return the total row count.

**CSV**

1. Open the output file once; create a `csv.writer` (or `DictWriter`) and
   write the header row matching the contract's column order.
2. Iterate the same `part-*.jsonl` files line by line (no need to batch —
   a CSV writer is already row-at-a-time and cheap).
3. For each line: `json.loads`, then build a row tuple/list in the
   contract's column order. For `captured_at`, pass the ISO string through
   unchanged. For `attrs`, re-`json.dumps` the dict. For `price`/`in_stock`
   that are `None`, pass an empty string (not the string `"None"`) so the
   writer emits an empty field — check what value the writer needs to see
   to do that.
4. Track a running row counter; return it once every file is exhausted.

Both converters should be resilient to the raw data being split across
multiple `part-NNNN.jsonl` files — process them in sorted filename order,
one file at a time, and don't assume there's exactly one file.
