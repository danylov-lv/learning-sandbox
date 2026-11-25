# Hint 1

This is a tree, and the depth isn't given to you as a hardcoded number — you
need to traverse `parent_id` links downward from each root, level by level,
until there's nothing left to traverse. Think about what kind of SQL
construct lets a query call itself against its own output.
