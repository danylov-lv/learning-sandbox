Write the TTL clause first, then before writing `force_ttl`, ask yourself:
right after `load_from_raw` finishes, has ClickHouse actually looked at
each row's `scraped_at` and compared it to `now()` yet? What operation, in
general (not specific to TTL), is the one where ClickHouse revisits rows
that already landed in a part and decides to do something different with
them?

If your answer is "on INSERT" or "on SELECT", go re-read what a MergeTree
merge actually is and when ClickHouse decides to run one.
