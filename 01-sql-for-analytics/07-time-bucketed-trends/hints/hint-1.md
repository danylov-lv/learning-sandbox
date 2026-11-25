# Hint 1

Three different questions are hiding in this task: "how much raw data," "how many
distinct things," and "what's the price level." Each needs a different aggregate
function applied to a different column (or combination of columns). Don't try to
derive one from another — compute each independently in the same `GROUP BY`.

Think about what "double-counted" actually meant in the backstory: which column, if
you `COUNT(*)` on it instead of counting distinct values, would inflate exactly the
way the sales team complained about.
