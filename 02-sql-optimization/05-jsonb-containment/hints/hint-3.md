# Hint 3

`CREATE INDEX ... ON products USING gin (attrs)` (default `jsonb_ops`) or
`CREATE INDEX ... ON products USING gin (attrs jsonb_path_ops)` will both
turn the `@>` filter into a Bitmap Index Scan.

Once you've done that, look at the plan again. The GIN index gets you a
fast bitmap over matching rows, but `ORDER BY created_at DESC LIMIT 48`
still has to sort whatever the bitmap heap scan hands it. That sort is not
free, even on a small-ish result set — it's just much cheaper than sorting
the whole table. Decide for yourself whether that residual cost is
acceptable for the SLA, or whether it points at a second, separate
opportunity you are not required to chase for this task.
