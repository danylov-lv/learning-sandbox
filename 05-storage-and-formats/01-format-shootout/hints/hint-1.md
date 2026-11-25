# Hint 1

"Streaming" here means: at no point does the process hold every row of
`data/raw/*.jsonl` in memory at the same time. Read the input a bounded
number of lines (or bytes) at a time, convert that chunk, write it out, and
let it go before pulling in the next chunk. At 5 GB this is the difference
between a script that runs in a few minutes with flat memory and one that
gets OOM-killed halfway through.

The other thing to notice: the raw JSON has no schema at all. Every line is
just text; `json.loads` hands you Python `int`/`float`/`str`/`bool`/`None`/
`dict` values with no declared types attached. Parquet, on the other hand,
wants you to commit to a column type up front (int64, float64, a timestamp
with a timezone, ...). That decision — what type each column *should* be,
and what to do about the field that's sometimes present and sometimes
`null` — is work you have to do, not something the converter can discover
by inspecting one row. Look at what `generate.py` actually writes for
`price`, `in_stock`, and `captured_at` on non-200 rows before you decide how
to handle them.
