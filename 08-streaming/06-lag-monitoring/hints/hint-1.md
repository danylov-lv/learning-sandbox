Start from what the two harness calls actually give you.
`end_offsets(TOPIC)` and `committed_offsets(GROUP_ID, TOPIC)` both return a
plain `dict` keyed by partition number. Look at their docstrings in
`harness/common.py` before writing anything — in particular, what value
`committed_offsets` puts in the dict for a partition that has never had an
offset committed. That value is not a lag; it's a sentinel you have to
special-case.

Think about the shape of "one snapshot" as a single unit of work, not a
sequence of independent writes: a snapshot is N per-partition rows plus
(maybe) one alert row, and either all of it lands in Postgres or none of
it does. That's the same one-transaction discipline task 04 used for a
different reason — there, atomicity was about not double-counting under
redelivery; here, there's no redelivery at all, but a half-written
snapshot (some partitions' rows present, others missing because the
process died mid-loop) would silently corrupt every total computed from
it afterwards.

Also notice what the task is *not* asking you to do: don't open a
`Consumer` that subscribes or polls TOPIC. Every value you need comes from
two read-only broker-metadata calls; if you find yourself writing a poll
loop, you've drifted into building a consumer instead of a monitor.
