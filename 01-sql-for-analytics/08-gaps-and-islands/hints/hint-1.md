# Hint 1

You need to turn a sequence of true/false flags into groups of consecutive equal
values, then measure each group. Row-by-row comparison against the previous row tells
you *where* a run breaks, but that alone doesn't give you something you can `GROUP
BY`. You need a value that stays constant within a run and changes between runs.

This is a well-known SQL pattern with a name — look it up before reinventing it from
scratch.
