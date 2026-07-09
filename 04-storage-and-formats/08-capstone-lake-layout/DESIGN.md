# DESIGN

Fill in each section with your own reasoning, once the pipeline is built
and the gates pass. Bullets are prompts to answer, not a checklist. Every
claim should point at a number you measured in tasks 01-07 or here.

## Layout and why

- Zones: what is bronze for, what is silver for, why two and not one?
- Partition key: why month, and what would go wrong at a different grain?
- Sort key: why `(source_id, captured_at)`, tied to your CP2 pruning
  measurement.
- Codec: which one, and the size/speed number from task 02 that justifies it.

## What 10x changes

- File counts today vs. at 10x, per partition and total.
- Listing cost: local filesystem vs. MinIO, tied to task 05's numbers.
- Compaction: what triggers it, how often, what it costs.

## Retention and lifecycle

- What ages out of silver, to where, and on what trigger.
- What changes about codec or tier choice for cold data.

## What I would do differently with Iceberg/Delta everywhere

- Where hive-partitioned Parquet already strained in tasks 04-06.
- What a table format buys you there that a folder convention cannot.
