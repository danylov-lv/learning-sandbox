# Hint 1

Think of this task as two separate problems that happen to share a table.
Problem one: what does a "good" record look like, expressed as rules a
computer can check without you eyeballing rows? Problem two: given a set of
rows where some pass those rules and some don't, how do you get the passing
ones into one table and the failing ones into another, twice in a row,
without the second run doing anything different from the first?

Solve them separately before trying to wire them together in a DAG. Load a
day's staging rows into a plain pandas DataFrame in a scratch script first,
get the schema validating correctly against it, and only then worry about
Airflow tasks and idempotent writes.

Also: read what `strict` does on a pandera `DataFrameSchema` before you
decide what to set it to. It's not a cosmetic setting.
