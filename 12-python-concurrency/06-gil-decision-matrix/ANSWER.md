# GIL Decision Matrix — Backed by Measurements

Fill in every section using the actual numbers `uv run python tests/
validate.py` prints from your own `baseline-local.json` -- not general
asyncio folklore, not numbers from someone else's machine.

## Decision matrix

[fill in -- a Markdown table with one row per workload, naming the best
tool, the speedup you measured for it vs `run_sequential`, and a one-line
why. Pull the numbers straight out of your baseline run.]

| Workload type | Best tool | Measured speedup vs sequential | Why |
| --- | --- | --- | --- |
| cpu_bound | [fill in] | [fill in] | [fill in] |
| io_bound | [fill in] | [fill in] | [fill in] |

## CPU-bound: why threads don't help

[fill in -- explain, in terms of the GIL, why `run_threads` barely beat (or
even lost to) `run_sequential` for `cpu_bound` in your baseline, even
though you asked ThreadPoolExecutor for N-way concurrency. Reference the
actual thread speedup number you measured.]

## I/O-bound: why the GIL doesn't matter here

[fill in -- explain why threads AND asyncio got a large speedup on
`io_bound` despite the same GIL being present the whole time. What does
`time.sleep()` (standing in for a blocking network/disk call) do to the
GIL that a Python-level compute loop does not?]

## Process pool overhead: when it isn't worth it

[fill in -- ProcessPoolExecutor has real costs (process startup, pickling
arguments and results across the process boundary) that ThreadPoolExecutor
doesn't. Describe a workload where those costs would eat the entire
speedup you measured -- what has to be true about the size of an
individual work unit for multiprocessing to pay off?]

## Rules of thumb

[fill in -- a short, bulleted decision heuristic you would actually apply,
before writing any code: given a new workload, how do you decide asyncio
vs threads vs processes?]
