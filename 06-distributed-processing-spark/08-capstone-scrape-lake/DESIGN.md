# DESIGN

Fill in each section with your own reasoning, once CP1 and CP2 both pass.
Bullets are prompts, not a checklist. Every claim should point at a
number from this task or from tasks 01-07.

## Silver lake layout and why

- Partition key: why month, not a coarser or finer grain.
- Join strategy: why both reference joins broadcast safely, and where
  that stops being true.
- File count per partition: your CP1 numbers, and whether they'd still
  hold at 50M+ rows.

## The shuffle-tuning pass

- Concrete knobs changed between naive and tuned, each tied to a
  plan-shape or Spark-UI observation, not just "it got faster."
- What the naive SortMergeJoin cost that the tuned BroadcastHashJoin
  didn't — point at a number from the Spark UI.
- Was the wall-clock gap convincing on its own, or mostly the plan
  evidence? Say which, honestly.

## When this pipeline would NOT need Spark

- Task 07's calibration verdict, applied at this task's scale.
- Roughly where that verdict flips, and why.
- Would you keep this Spark pipeline if volume never grew past this
  task's committed dataset?
