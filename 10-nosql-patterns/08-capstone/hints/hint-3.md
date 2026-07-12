# Hint 3 -- concrete shape

**`produce` / `ensure_group`:** small and mechanical. `ensure_group` creates
the group with `MKSTREAM` at start-id `'0'` (not `'$'`) so it doesn't matter
whether you call it before or after the first `produce()` -- everything
ever written is still eligible for `'>'` delivery. Catch `BUSYGROUP` on
re-creation, nothing else.

**`materialize`:** one upsert per entry (or one bulk write for the whole
batch -- much faster over ~tens of thousands of entries than a round trip
per document, worth reaching for once the single-entry version works),
filtered by product_id, that only overwrites price/category/scraped_at/
event_id when the new `(scraped_at, event_id)` beats what's already stored
(or nothing is stored). Two ways to get this right:

  - Read-modify-write in application code: fetch the existing document (if
    any), compare in Python, write back only if newer. Simple, and correct
    as long as nothing else is concurrently touching the same product_id --
    true for how the validators drive this (sequential consumers, never two
    processes materializing the same batch at once).
  - A single `update_one` whose update is a PIPELINE (a list of stages, not
    a plain dict) rather than a plain `$set`, so the new value for each
    field can be a `$cond` comparing the incoming watermark against
    `$<field>`'s CURRENT value in the same atomic operation, with
    `upsert=True`. This is the version that stays correct even under
    concurrent writers, since the comparison and the write happen as one
    server-side operation -- no separate read.

Either is a legitimate answer to `materialize`; the validators only check
the resulting `t08_state` contents, not which approach you used. Store
`product_id`, `price`, `category`, `scraped_at`, `event_id` per document --
`current_state_summary` needs to read all four back out.

**`run_consumer`:** `XREADGROUP GROUP group consumer COUNT n STREAMS
stream_key >` in a loop, `materialize` each batch, `XACK` the entry IDs in
that batch, track how many you've processed. Stop when you've hit
`max_messages` (if given) or a read comes back empty. A batch COUNT in the
low hundreds keeps the round trips reasonable over the corpus sizes here
without needing to tune anything.

**`reclaim_and_run`:** `XAUTOCLAIM stream_key group consumer min_idle_ms
start_id COUNT n`, starting `start_id='0-0'`, `materialize` + `XACK`
whatever it claims, then follow the cursor it returns until a call comes
back with nothing claimed and a cursor of `'0-0'` (a full pass with nothing
left).

**How per-category counts fall out of `t08_state` for free:** each document
already stores the ONE category that product belongs to (its real catalog
category, joined in before the event ever reached `produce`). `count` is
just the collection's document count, `price_sum` is the sum of the stored
`price` field across all documents, and `per_category_count` is a `GROUP BY
category` over the same collection -- no second data source, no rejoining
anything, because by the time a document exists in `t08_state` it already
carries everything `current_state_summary` needs.

**`DESIGN.md`:** cite the actual CP2 numbers when you fill in "Crash
recovery flow" -- how many entries got reclaimed, and (if you want to look)
how many products in the corpus needed a genuine overwrite across the crash
boundary versus a fresh insert.
