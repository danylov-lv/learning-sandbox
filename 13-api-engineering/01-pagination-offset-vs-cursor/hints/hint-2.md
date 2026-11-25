The technique is **keyset pagination**, also called **seek-method** pagination
or just **cursor** pagination. Instead of describing a page by its position
("skip 199,900, take 20"), you describe it by a *value*: "give me the rows
whose `id` comes after the last one I already saw."

Because `id` is indexed and the rows are read in `id` order, the database
can seek directly to that value with an index lookup and read forward
exactly `limit` rows -- no earlier rows are touched at all, so page 2,000
costs the same as page 1. The query shape is:

```
WHERE id > :cursor ORDER BY id LIMIT :limit
```

`:cursor` is not a page number -- it's the `id` of the last row the caller
already has (0 or omitted for the very first page). The response hands back
the last `id` it returned as `next_cursor`, and the caller passes that
straight back in as the next request's `cursor`. There's no bookkeeping of
"which page am I on" anywhere; the cursor *is* the position, encoded as the
one column the ordering already depends on.

This also gives you something OFFSET pagination can't: you can jump straight
to an arbitrary depth by just picking a cursor value, without walking
anything before it -- there's no "page 2,000" concept to compute your way
into. Two things still need deciding: what to clamp `limit`/`cursor` to when
they're garbage, and how to build `next_cursor` (including the `null` case).
The next hint gets concrete about both, plus how to reuse a connection
across requests instead of opening one per call.
