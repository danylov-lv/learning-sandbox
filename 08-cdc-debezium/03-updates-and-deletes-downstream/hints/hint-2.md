Three of the four ops you'll see (`r`, `c`, `u`) all resolve to the same
action: upsert `replica.offers` from `after`, keyed on `offer_id`. You
don't need to branch on `r` vs `c` vs `u` separately -- treat them as one
case.

`d` is the only op where you read the key from `before` instead of
`after`, because `after` is `None` on a delete -- there is no new row to
upsert, only an old `offer_id` to remove. Delete the row matching that
`offer_id` from `replica.offers`.

Tombstones (decoded payload `None`) never reach your `apply_change`
function -- the given loop already filters those out before calling it.
