# Hint 3 — concrete approach

Shape of the invocation (fill in the transform yourself):

```
mkdir -p data/batch/outputs
parallel --jobs <N> --joblog data/batch/joblog.txt \
  '<per-file command reading {} and writing to data/batch/outputs/{/}>' \
  ::: data/batch/inputs/*.json
```

The per-file command needs to read one input JSON's `listings` array and
emit the five required fields (`page_id`, `listing_count`,
`total_price_usd`, `avg_price_usd`, `categories`) as JSON to stdout — a
single `jq` filter can do the whole reshape in one call per file, the
same kind of transformation task 01 already had you write. Whatever you
use, make sure `mkdir -p data/batch/outputs` runs *before* `parallel`
starts firing off jobs that write into it.
