# Hint 1

Task 05's contract already tells you, per row, which check failed. That's
exactly the signal you need to tell "this is drift" from "this is normal
invalid data" apart — you don't need anything new to detect it, you need to
look at the *shape* of the failures you already get back, aggregated across
the whole batch rather than row by row.

Ask yourself: if 99% of a day's rows fail the exact same check for the exact
same reason, what does that suggest that a random 1% of rows failing an
assortment of different checks doesn't?

For the string-price problem, don't try to fix it inside the pandera schema
itself. Pandera checks whether data is already correct; it's not a parser.
The parsing has to happen before the schema ever sees the column.
