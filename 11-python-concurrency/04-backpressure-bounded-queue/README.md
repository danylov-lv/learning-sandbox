# 04 -- Backpressure / Bounded Queue

## Backstory

Your async scraping pipeline has two halves: a producer that fetches pages
fast, and a consumer that parses and writes them to storage slowly. You wire
them together the obvious way -- a shared buffer the producer drops items
into and the consumer drains from at its own pace:

```python
buffer = []  # or: queue = asyncio.Queue()  -- no maxsize means the same thing

async def produce(n):
    for i in range(n):
        buffer.append(make_item(i))   # never blocks, never waits for the consumer

async def consume():
    while buffer:
        item = buffer.pop(0)
        await slow_write(item)        # takes real time
```

On a laptop against 50 test pages this looks fine -- runs, finishes, correct
output. Point it at a job with 500,000 pages and the process's memory climbs
in a straight line for the entire run, because the producer has no way to
know the consumer is behind and no reason to slow down: it just keeps
fetching and appending. By the time the consumer has drained a tenth of the
buffer, the producer has already materialized the other nine-tenths in
memory, waiting. Peak memory ends up proportional to how many items you
*feed* the pipeline, not to how much work is genuinely in flight at any one
moment -- which defeats the entire point of a pipeline (bounded, steady-
state resource use) and will eventually OOM a long-running job that would
otherwise complete fine, just slower.

The fix isn't a faster consumer or a bigger machine -- it's giving the
producer a way to feel resistance: a **bounded** buffer that makes adding to
it block once it's full, so the producer is forced to slow down to the
consumer's pace. This is backpressure -- the same idea as TCP flow control,
or a factory line where the input hopper only holds so many parts before the
feeder arm has to wait.

## What's given

- `src/pipeline.py` -- an `async def run_pipeline(produce_n, consume_fn,
  max_in_flight)` scaffold. The docstring spells out the exact contract:
  produce `produce_n` items in order, bound how many are in flight at once
  to `max_in_flight`, consume each exactly once, shut down cleanly, return a
  result dict. Currently `raise NotImplementedError`.
- `harness/common.py`'s `measure_peak_memory` (peak *traced* allocation via
  `tracemalloc`, not RSS -- portable and reproducible across machines) and
  `snapshot_tasks` / `leaked_tasks` -- both used by the validator, and both
  fair game to poke at yourself while testing your implementation by hand.

## What's required

Implement `run_pipeline` in `src/pipeline.py` so that:

1. It produces items `0 .. produce_n - 1`, in order.
2. At no point are more than `max_in_flight` items produced-but-not-yet-
   consumed -- enforced by making the producer actually wait (block) when
   the buffer is full, not by a manual counter-and-poll loop.
3. `consume_fn` is awaited exactly once per item.
4. It shuts down cleanly: every task it starts either finishes or is
   awaited/cancelled before `run_pipeline` returns -- nothing left running
   in the background.
5. It returns `{"consumed": <int>, "checksum": <int>}` -- `consumed` is the
   total number of items consumed, and `checksum` is the sum of the indices
   of every consumed item. Summing is order-independent on purpose: it
   doesn't matter which order multiple consumers happen to finish in, only
   that every index contributes to the sum exactly once.

Peak memory during a run must stay roughly flat as `produce_n` grows for a
fixed `max_in_flight` -- that's the property the validator actually
measures (see below), not just "doesn't crash on the test input."

## Completion criteria

Run, from this task's directory:

```bash
uv run python tests/validate.py
```

It:

- Runs a large `produce_n` and asserts every item was consumed exactly
  once (the returned checksum matches an independently computed expected
  value, and `consumed == produce_n`).
- Measures peak *traced* memory (`tracemalloc`, not RSS) for `produce_n = N`
  and again for `produce_n = 4N`, with the same small `max_in_flight` both
  times, and asserts the second peak is at most ~2x the first -- a properly
  bounded pipeline stays roughly flat; an unbounded buffer would show
  roughly 4x, tracking the 4x growth in total items produced.
- Asserts no `asyncio.Task` is left running (leaked) after either run.
- Prints `PASSED` with the observed counts and memory ratio, or
  `NOT PASSED: <reason>` and exits 1 -- including on the stub's
  `NotImplementedError`.

## Estimated evenings

1

## Topics to read up on

- `asyncio.Queue` and the `maxsize` argument
- Backpressure / flow control as a general concept (not asyncio-specific)
- Producer/consumer pipelines with a worker pool
- Sentinel values for signaling shutdown through a queue
- `Queue.task_done()` / `Queue.join()`
- `tracemalloc` peak traced allocation vs RSS

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the mock-peer semantics, and the verification philosophy behind every task
in this module -- spoilers. Don't read it before finishing this task.
