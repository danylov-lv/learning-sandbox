# Hint 2

Use `WITH RECURSIVE`. The anchor member selects the 8 root rows
(`level = 0`), carrying along the root's own id and name as extra columns.
The recursive member joins `categories` to the previous result on
`categories.parent_id = previous.id`, propagating the same root id/name
forward at every depth. The result is a flat table mapping every category in
the whole tree to the root it descends from — that's your building block for
every other column you need.
