# Hostile Review: Price History Storage

Eight questions a skeptical colleague would ask about this specific design.
Answer them inside `DESIGN.md`, under `## Hostile review responses`, as
`### Q1` .. `### Q8` -- restate each question, then answer it with actual
numbers from your capacity model where a number is the honest answer.

## Q1

Change-only storage keeps only the rows where the price actually changed,
which your capacity model shows is a large reduction in stored rows and
bytes. But the charting read needs a *continuous* daily series, including
every day the price didn't move. Walk through exactly what a "1-product,
1-year" query has to do to reconstruct that continuous series under
change-only storage, and say concretely -- using your compressed-bytes
numbers for both the full and the change-only variant -- why that
reconstruction cost is or isn't worth the storage savings.

## Q2

Your ordering/clustering key was chosen to make one read pattern cheap.
State plainly what that same key costs the "top-N price movers per
category per day" analytics read: which columns get scanned that wouldn't
need to be if the key had been chosen for that query instead, and roughly
how much more data that read has to touch as a result.

## Q3

A price observation from 34 days ago just arrived, late, because a scraper
worker got stuck retrying against a target site. The partition or segment
it belongs to is already sitting in the cold tier and may already have been
compacted. Walk through exactly what has to happen -- at the storage layer,
and at any cache or materialized-view layer sitting in front of it -- for
that late row to become visible and consistent with anything already served
to a client.

## Q4

Marketing wants a new `currency_of_record` column added to every historical
row, effective immediately, with no downtime. What happens to the 5 years
of already-written, already-compressed partitions -- is this a
metadata-only change, a full rewrite of historical data, or something in
between? What does it cost, and does your capacity model change as a
result?

## Q5

One category, out of roughly three dozen, is 40x more volatile than the
rest -- its products change price constantly, all day. Does your per-day
observation rate, your change-only fraction, and your hot-tier sizing still
hold when one category dominates the write volume this unevenly? What is
the first thing in this design that breaks, and how would you notice before
a client does?

## Q6

Your hot/cold boundary sits at a fixed number of days. Justify that number
against the actual read pattern: what fraction of realistic "1-product,
1-year" range queries fall entirely inside the hot window versus spill into
the cold tier, and what does that spillover do to query cost or latency at
the boundary?

## Q7

Continuous small writes into a columnar layout need periodic compaction to
keep compression ratio and query performance where your capacity model
assumes they are. What does your write path's compaction cadence cost in
write amplification, and what is the failure mode if compaction falls
behind the firehose for an extended period?

## Q8

Five years from now, this system has 10x the tracked products. Which part
of this design -- the ordering key, the partitioning granularity, the
hot-tier window, the change-only threshold -- is the first to need
re-architecting, and why? Point at the specific number in your capacity
model that crosses an uncomfortable threshold first.
