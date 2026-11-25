There are two separate scaffolds here and they test two separate things.

`setup_topic.py` just needs a `create_topic()` call with
`cleanup_policy="compact"` and an `extra_config` dict. Go read
`harness/common.py`'s `create_topic` docstring and signature — it already
does the "idempotent if it exists" and the config-merging for you. The two
knobs the TODO names (`segment.ms`, `min.cleanable.dirty.ratio`) are just
entries in that `extra_config` dict, both passed as strings (Kafka configs
are always strings over the admin API, even for numbers).

`consumer.py`'s poll loop is the same shape you've already written in task
02 or 03: `poll()`, `None` means idle (accumulate idle time), a real message
means reset idle time and do the work. The new part is `upsert_latest` —
that's a SQL problem, not a Kafka problem. Think about what "last write
wins, but don't let an older write clobber a newer one" means as a single
`INSERT ... ON CONFLICT` statement with a `WHERE` clause on the `DO UPDATE`.
