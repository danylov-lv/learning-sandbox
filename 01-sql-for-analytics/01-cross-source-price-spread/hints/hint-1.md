# Hint 1

Start by figuring out, for every product, which root category (level 0) it
ultimately belongs to. Do that as a separate step before you touch
`price_snapshots` — resolving the category tree and aggregating snapshots
are two different concerns, and mixing them in one giant join is where fan-out
bugs creep in.
