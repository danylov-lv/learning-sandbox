# 09 -- Load Test and Bottleneck Hunt

## Backstory

`GET /catalog/{category_id}` shipped months ago. It is a normal
product-listing widget for the marketplace: give it a category, get back a
page of products, each one already carrying its seller's name and tier so
the frontend never has to make a second call. Every response it has ever
returned is correct. Nobody filed a bug against it.

Then category 9 ("Headphones & Audio") got featured on the homepage, and
the traffic on this one endpoint went from "a trickle" to "a lot of people
hitting it at once." Support tickets started arriving: the page spins for
almost a second, sometimes longer, and it gets *worse*, not better, the
more people are browsing at the same time. Nothing about the query got
bigger -- it's still 20-30 rows. What changed is concurrency. This task
hands you that endpoint exactly as it shipped: a real, running FastAPI app,
not a stub. Your job is to find out why it falls over under load and fix
it, without changing a single byte of what it returns.

This is a different kind of exercise from most of this module. There is no
`NotImplementedError` telling you where to start, and no docstring spelling
out what's wrong. The method is the exercise: **measure, form a hypothesis,
fix ONE thing, re-measure.** You will need a load-testing tool for this
(the harness gives you one) and a way to look at what the app is actually
doing while it's under load, not just what it returns to a single request.

## What's given

- `src/app.py` -- a complete, working FastAPI app. `GET /catalog/{category_id}
  ?limit=&offset=` pages the shared, read-only `shop.products` table filtered
  by category, ordered by id, and attaches each product's seller name/tier
  from `shop.sellers`. Returns
  `{"category_id", "limit", "offset", "items": [{"id", "title", "price",
  "seller_name", "seller_tier"}, ...]}`. A single request against it, at any
  time, returns the right answer. Never write to `shop`.
- `baseline.py` -- bombards the app as shipped and records this machine's
  stock throughput/p95 latency to a gitignored `catalog-load-local.json`.
  Run this BEFORE you change anything.
- `tests/validate.py` -- the correctness + relative-throughput check you run
  AFTER you believe you've fixed it.
- The module harness: `harness.load.bombard()` (a small asyncio load
  generator -- concurrency, duration or request count, and it hands back
  RPS/p50/p95/p99), and `harness.service.run_app_subprocess` (launches the
  app as a REAL separate OS process on an ephemeral port, which is how both
  `baseline.py` and `tests/validate.py` run it -- see "Why a subprocess"
  below).
- The shared `shop.products` / `shop.sellers` corpus. `shop` is clean and
  properly indexed for this task's query shapes -- if you find yourself
  reaching for `CREATE INDEX`, you're looking in the wrong layer. Whatever is
  slow here is slow in the Python/FastAPI code, not in Postgres's query plan.

## What's required

1. Run `baseline.py` against the app exactly as shipped. Look at the numbers
   it prints -- not just the RPS, but the gap between p50 and p95/p99.
2. Find out WHY throughput is low and tail latency is high under
   concurrency. You have `bombard()` to reproduce the symptom on demand, and
   you have the running app -- add whatever instrumentation you need
   (timing prints, `pg_stat_activity` queries against the shared Postgres,
   counting how many queries one request actually issues, watching whether
   the app's process even uses more than a sliver of one CPU core under
   load). Nothing here requires code you haven't already got: a plain
   `curl`/`httpx` call plus `bombard()` plus your own eyes on the numbers is
   enough.
3. Fix what you find. There is more than one thing wrong, and they are
   independent of each other -- you can fix them one at a time and expect to
   see the numbers move each time you do. You do not need to rewrite the
   endpoint; each fix is a small, targeted change. **The response shape and
   content must not change** -- same fields, same values, same ordering,
   for the same request. Only how fast and how consistently it answers under
   load should change.
4. Re-run `baseline.py`'s numbers informally (or just watch `bombard()`
   output) after each fix to confirm you actually moved the needle before
   moving to the next hypothesis. A fix that doesn't measurably help either
   wasn't the bottleneck or wasn't applied where you think it was.

### Why a subprocess

`baseline.py` and `tests/validate.py` both launch your app via
`run_app_subprocess` -- a real, separate `uvicorn` process, talking over a
real TCP socket -- rather than running it in-process next to the load
generator. This is deliberate: the thing you're hunting is an OS-level /
event-loop-level bottleneck. If the app ran as a coroutine inside the same
process and event loop as the thing bombarding it, cooperative scheduling
between "the load" and "the app" would hide exactly the class of problem
this task is about. Keep that in mind while you investigate too -- testing
your app in-process (e.g. with `httpx.ASGITransport`) will not reproduce the
symptom, even after you understand it.

## Completion criteria

Two steps, run from this task's directory:

```bash
# 1. before touching src/app.py, record this machine's stock numbers:
uv run python baseline.py

# 2. after fixing src/app.py, check correctness + the relative throughput bar:
uv run python tests/validate.py
```

`tests/validate.py` checks, in order:

- **Correctness first.** Several `/catalog/{category_id}` requests (a large
  category at a shallow and a deep offset, a small category's trailing
  partial page, an empty root category, and a couple of out-of-range
  `limit`/`offset` values) are checked against an oracle the validator
  computes itself with independent SQL straight from `shop.products` /
  `shop.sellers` -- never trusting your app's own output. A "fix" that
  returns wrong, missing, or extra rows fails here regardless of how fast it
  is.
- **Then relative throughput.** Only if correctness passes: your app is
  bombarded with the same load shape `baseline.py` used, and the result is
  compared against `catalog-load-local.json` on BOTH an RPS ratio and a p95
  ratio against the stock baseline -- relative to THIS machine, never an
  absolute millisecond/RPS number. If the baseline file is missing, it tells
  you to run `baseline.py` first instead of crashing.

Prints `PASSED: ...` with the observed ratios, or `NOT PASSED: <reason>` and
exits 1.

## Estimated evenings

1-2

## Topics to read up on

- The N+1 query pattern -- what it is, why ORMs are especially prone to it,
  how to spot it from query counts/logs rather than by reading code
- `asyncio`'s cooperative scheduling model: what "blocking the event loop"
  actually means, and why a synchronous call inside `async def` doesn't
  behave like an `await`
- `run_in_threadpool` / `asyncio.to_thread` -- handing a blocking call off a
  single-threaded event loop
- Connection pool sizing: what `min_size`/`max_size` control, what happens
  to a request when every pooled connection is checked out, and why "just
  make the pool huge" isn't automatically the right answer either
- `pg_stat_activity` -- watching what a Postgres instance is actually doing
  while under load
- Percentile latency (p50 vs p95 vs p99) and why averages hide the story a
  load test is trying to tell you
- Reading a load generator's own output (RPS, error rate, latency spread) as
  a diagnostic signal, not just a pass/fail number

## Off-limits

`.authoring/design.md` (at the module root) holds the harness API contract,
the `shop` schema, the committed ground-truth values, and the verification
philosophy behind every task in this module -- spoilers. Don't read it
before finishing this task.
