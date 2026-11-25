Both stores can answer every query in this task -- that was never in
doubt. MongoDB matching a nested field or an array-membership predicate is
native to how it queries documents; Postgres matching the same shapes
inside a `jsonb` column is native too, once you reach for the right
operator. Neither engine is "wrong" for this data. The actual question this
task is testing is narrower: what index does EACH one need to answer these
specific predicates without reading every row/document to check it by hand?

Think about the containment predicate first: "category is electronics, AND
in_stock is true, AND tags contains sale." In Mongo terms this is three
conditions ANDed together, one of them (`tags`) against an array field. In
Postgres/JSONB terms, notice that all three conditions describe a SHAPE the
document must contain -- `{"category": "electronics", "in_stock": true,
"tags": ["sale"]}` -- rather than three separate column comparisons. That
reframing (three ANDed conditions vs. one containment check) is exactly why
Postgres reaches for a different operator (`@>`) than a normal `WHERE col =
value AND col2 = value2` -- and why that operator needs a different kind of
index than an ordinary B-tree.

Before writing any code, go find: which Postgres index type supports `@>`
on a jsonb column (a plain B-tree does NOT), and which Mongo index shape
(single field? compound? does field order matter?) actually gets chosen by
the planner for a filter with an array-membership term mixed in with plain
equality terms.
