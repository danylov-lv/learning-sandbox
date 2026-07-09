# Hint 1

`attrs @> '{"brand": "Peakline"}'` is not an equality or range comparison —
it asks "does this JSON document contain this structure." B-tree indexes
(the kind you saw in task 03) are built for ordering and equality. Ask
yourself: does a B-tree even know how to compare two JSONB values for
containment?

Look at what index types Postgres offers besides B-tree.
