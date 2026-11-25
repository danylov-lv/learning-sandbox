Start with `SetDedup`. Redis's `SADD key member` already returns exactly what
you need: the number of elements that were actually added (0 or 1 for a
single member). That number IS your answer to "was this new?" -- no separate
read (`SISMEMBER`) before the write, no race, no extra round trip. One Redis
command, one boolean.

Once that's passing, sit with the question the README is actually asking:
what does this structure cost as the crawl grows from thousands of urls to
tens of millions? Every distinct url becomes a permanent member of that SET,
in full, forever. Nothing here gets smaller. If you had to hold urls seen
across a year-long crawl, what would that SET's memory footprint look like,
and would you be comfortable with it? Don't answer in code yet -- just sit
with the number. That discomfort is exactly what the Bloom filter half of
this task exists to address.
