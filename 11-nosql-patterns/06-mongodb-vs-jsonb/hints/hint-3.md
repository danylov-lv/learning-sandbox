The partial update, on both sides, is about changing ONE field of a
document without touching (or re-sending) the rest of it.

Postgres: `jsonb_set(target jsonb, path text[], new_value jsonb)` returns a
NEW jsonb value with one path replaced -- it does not mutate anything in
place at the SQL-value level. You still write it back with a normal
`UPDATE ... SET doc = jsonb_set(doc, '{price}', <jsonb value>) WHERE
product_id = ...`. The `path` argument is a text array literal like
`'{price}'` for a top-level key (this task never touches a nested key for
the update, only `price`, which sits at the top of the document). Whatever
you pass as the new value must already BE jsonb -- a bare Python float
handed to psycopg won't automatically become a jsonb scalar inside
`jsonb_set`'s second argument unless you wrap it (`to_jsonb(...)`, or bind
it through psycopg's own jsonb adapter).

MongoDB: `$set` with a field name is enough -- `{"$set": {"price":
new_price}}` in an `update_one({"product_id": ...}, {...})` call rewrites
only that key of the matching document; every sibling key (`specs`,
`tags`, `seller`, ...) is left as-is by the driver/server, no re-encoding
of the whole document required from your side.

On the containment predicate itself: resist the urge to build it as three
separate boolean checks in Postgres just because that's how you'd write it
in SQL against normal columns. Build the exact object/array shape you want
to test for containment against, as one jsonb value, and let `@>` do the
"does the document contain (at least) this shape" check in one operator
call -- that's what lets the GIN index answer it in one scan instead of
Postgres evaluating three separate predicates row by row.

For the write-up in NOTES.md: think concretely about what changes if a
SIXTH predicate field shows up in tomorrow's query on each side. On the
Mongo side, does your existing compound index still work, or do you need a
new one? On the Postgres side, does your GIN index need to change at all,
or does the SAME index already cover the new field for free because of how
GIN indexes jsonb key/value pairs? That difference is worth writing down --
it's one of the sharpest points of contrast between the two approaches.
