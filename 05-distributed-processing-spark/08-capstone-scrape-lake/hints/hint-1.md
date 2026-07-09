# Hint 1 — where to start

This capstone is every earlier task in this module, run back to back, on
one dataset. CP1 is task 03's broadcast joins plus task 06's controlled
partitioned write, done in a single function. CP2 is task 02's partition
tuning plus task 03's broadcast-vs-shuffle decision plus task 05's
instinct for what makes a join expensive, aimed at one deliberately
shuffle-heavy query you both write and then tune.

Before writing any code for CP1, go reread task 03's `broadcast_enrich`
and task 06's `write_month_partitioned` side by side — CP1's contract is
close to literally those two stitched together, in that order (join
first, derive the partition column and control file count second).

Before writing CP2, work out on paper (not in code) what makes the
naive form of the job expensive: which join has no small side, and what
about the default configuration makes Spark's planner treat it as
"neither side is safe to broadcast." Only once you can say that in one
sentence should you write `run_naive`. `run_tuned` is then "change the
things that sentence identifies," not a grab-bag of unrelated config.
