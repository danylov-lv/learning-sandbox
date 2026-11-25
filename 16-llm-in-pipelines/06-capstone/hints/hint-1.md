You've already built (or seen the shape of) each of these three skills
separately elsewhere in this module — extraction, classification, dedup.
The new part here isn't the extraction/classification/dedup logic itself,
it's making each stage answer a second question alongside its normal
output: "how much do I trust this particular result?" A pipeline that runs
unattended over many records needs an honest answer to that question far
more than it needs perfect accuracy on every single record.

Build the three single-item functions (`extract_record`, `classify_record`,
`dedup_cluster`) and get them each returning something reasonable on clean
input before worrying about `run_pipeline`'s routing logic at all.
`run_pipeline` is mostly plumbing once the three stage functions exist and
behave — it calls each one, tags the results, and sorts records into two
buckets based on a field those functions already produced.

Think about what "never raise" actually requires in Python: it means every
place your code parses a model's response (JSON decoding, indexing into a
list, calling `float()` on something that might not be numeric) needs to be
somewhere you've decided in advance what happens if it fails, not
somewhere an exception is free to propagate up and take the whole batch
down with it.
