Multikey indexes: when you index a field whose value is an array (like
`tags`), MongoDB doesn't store one index entry per document -- it stores one
entry PER ARRAY ELEMENT, all pointing back to the same document. That's what
lets an equality match like "does `tags` contain `sale`" use the index at
all: the index has an entry for `"sale"` (among others) for every document
that has it in its tags array, and a normal index lookup on that value finds
them all. MongoDB calls this a "multikey index" and creates one automatically
the first time it notices the indexed field holds an array in some document
-- you don't ask for anything special in `create_index()`, you just index
the field the same way you'd index a scalar.

The one hard restriction to know: a single compound index can have AT MOST
ONE multikey field in it. You cannot build a compound index over two
different array fields at once (there isn't one here, so this is just
context) -- but you CAN mix one array field with any number of scalar fields
in the same compound index, which is exactly `graded_query()`'s situation
(`category` scalar, `in_stock` scalar, `tags` array).

Compound index field ORDER matters, and there's a well-known rule of thumb:
equality fields first, then sort fields, then range fields ("ESR"). All
three of `graded_query()`'s predicates are equality (`category = ...`,
`in_stock = ...`, `tags` contains a specific value is also an equality
lookup against the array), so pure equality-field ordering mostly comes down
to selectivity -- which field, filtered alone, narrows the collection down
the most? Put that one first, so the index can eliminate the most candidates
before it even needs to consult the next key component. Think about which of
`category`, `in_stock`, `tags` cuts down 20,000 documents hardest on its own.

For the nested field: `specs.color` is just a string path using MongoDB's
dot notation -- you index it exactly like you'd index any other field, by
passing that dotted string as the index key. Nothing about it being nested
one level down changes the `create_index` call shape.

For the aggregation pipeline itself: put `$match` as early as possible,
ideally as the FIRST stage. MongoDB's aggregation optimizer can push a
leading `$match` down so it runs against the collection directly (using an
index, if one matches its filter) before any `$group`/`$sort` work happens.
A `$match` placed after other stages, or a filter expressed only inside
`$group`'s accumulators, won't get that treatment.
