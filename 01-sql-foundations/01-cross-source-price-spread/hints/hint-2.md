# Hint 2

Since every product's category is a level-3 leaf, and the tree has exactly 4
levels (0..3), you can walk from leaf to root with a chain of joins on
`categories.parent_id`: leaf -> its parent (level 2) -> that parent (level 1)
-> that parent (level 0). Build a small lookup (leaf category id -> root
category name) first, as its own CTE, and confirm it produces exactly one row
per leaf category before joining it to anything else.
