# Hint 1

A plain directory of Parquet files has no concept of "the write that is
happening right now." A reader that lists the directory mid-write sees
whatever files have landed so far — some of a batch, none of it, or all of
it, purely depending on timing. A table format's entire value proposition
is turning "a pile of files" into "a sequence of numbered, all-or-nothing
commits," and every feature this task asks you to build (multi-commit
append, schema evolution, time travel, compaction) is really the same
underlying idea used four different ways: the table's current state is
never "the files on disk," it is "what the transaction log says the files
on disk mean, as of some version."

Before writing code, go look at what actually lands on disk after a single
`write_deltalake` call to a fresh directory. There is a `_delta_log/`
subdirectory next to the Parquet files — open the JSON file inside it. That
file, not the Parquet files' mere presence, is the source of truth a reader
consults. Everything else in this task follows from taking that idea
seriously: appending is adding entries to that log, not just dropping more
Parquet files next to old ones; time travel is replaying the log only up to
some version; schema evolution is a log entry that changes how existing
files are interpreted, not a rewrite of those files.

Also worth sitting with before you code: why does splitting the last
month's append into several separate write calls (rather than one) matter
for this task? What is different, on disk and in the log, between one
write of N rows and five writes of N/5 rows each?
