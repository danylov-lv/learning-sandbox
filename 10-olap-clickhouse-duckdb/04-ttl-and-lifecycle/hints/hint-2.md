TTL expiry is checked and enforced during a merge -- not on insert, not on
select, and not on any fixed schedule you can rely on inside a script that
runs for a few seconds and exits. `merge_with_ttl_timeout` even exists
specifically to stop ClickHouse from retrying TTL-driven merges too
eagerly on its own, which tells you something about how little you should
trust "it'll probably have merged by the time I query it".

There are two server commands, both operating on a table you name, that
force ClickHouse to reconsider a table's parts against its TTL expressions
right now rather than waiting: one is a general-purpose "merge everything
into one part" command that has TTL-checking as a side effect of any
merge it triggers; the other is named directly for TTL and tells
ClickHouse to recompute and apply TTL expressions for existing parts
without you needing to think about merges at all. Either is a legitimate
choice for `force_ttl`. Look up both by name in the ClickHouse docs for
`ALTER TABLE` and for `OPTIMIZE TABLE`.

Separately: think about why the validator computes its expected surviving
count by querying `observations_raw` with `WHERE scraped_at >= now() -
INTERVAL 15 MONTH` at the moment it checks your table, instead of using a
number written down in a file. What would go wrong if the expected count
were instead hardcoded from a run on a different day?
