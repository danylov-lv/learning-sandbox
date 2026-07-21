# Hint 2

For the physical layout: think in terms of a partitioning key (the coarse
grain a query can skip entire chunks of -- usually time-based, since
retention and tiering both operate on time) and a separate
ordering/clustering key within each partition (the fine-grained sort that
determines whether "one product's rows" are contiguous or scattered).
These are two different decisions. A partition scheme built around
calendar time (e.g. monthly) supports retention/expiry cleanly. An
ordering key that leads with the product identifier is what makes the
charting read cheap -- but check what that does to a query that wants "all
products, one day," which no longer benefits from that same ordering.

For the write path: a firehose of small, frequent observations doesn't
want to become one file per observation -- think about batching writes
into larger units and what has to happen afterward (compaction) to keep
the file/part count and compression ratio healthy. Consider what happens
if a batch arrives out of time order, or late.

For hot/cold tiering: the boundary is a number of days, and it should be
justified by how far back the dominant read actually needs low-latency
access, not by an arbitrary round number. Cheaper cold storage usually
means slower reads and/or coarser granularity, not "the same but discounted."

For the change-only variant: the storage saving is a straightforward
function of what fraction of observations changed. The cost is on the read
side -- reconstructing a continuous series means filling in every day that
has no row. Quantify both sides before deciding whether it's worth it.
