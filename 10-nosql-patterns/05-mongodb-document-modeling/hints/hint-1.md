Before writing any code, go through each business question and write down,
in plain words, which fields it filters on and which fields it groups by.
That list is the entire input to your indexing decision -- indexes exist to
serve specific filter/sort/group shapes, not fields in general.

- `per_category_stats()`: groups by `category`, aggregates `price` and
  `in_stock` across the WHOLE collection. No filter narrows this down --
  every document participates. Is there anything to prune here, or is this
  simply a full-collection aggregation that has to touch every row no matter
  what you index?
- `top_brands()`: groups by `brand` across the whole collection too. Same
  question.
- `graded_query()`: filters on THREE fields at once -- `category` (equality),
  `in_stock` (equality), and `tags` (checking whether an array CONTAINS a
  value). That last one is not like the other two: `tags` holds an array
  per document, not a scalar. What does it mean to build an index on a field
  whose values are arrays? (This has a name in MongoDB -- look it up before
  hint 2.)
- `nested_color()`: filters on `specs.color`, a field that lives one level
  down inside a sub-document, not at the top level of the document. Can you
  index a field that's nested like that? What syntax would you even use to
  refer to it?

Notice something: two of the four questions (`per_category_stats`,
`top_brands`) touch every document by design -- no index changes that. The
other two are the ones this task is really testing, because they're exactly
the kind of query a real dashboard or promo page hits over and over, and
they filter on fields that are NOT plain top-level scalars (one's an array,
one's nested). That's deliberate.
