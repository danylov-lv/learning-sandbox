Before touching any code, spend time with `baseline.py`'s own output.

It reports RPS and p50/p95/p99, all from the same run. Look at the *shape*
of that data, not just the headline RPS number. A single request against
this endpoint is fast -- you can confirm that yourself with one `curl` or
one `httpx.get()`. So whatever is happening only shows up once many
requests are in flight *at the same time*. That's the first real clue: the
problem isn't in what any one request does in isolation, it's in what
happens when N of them overlap.

Ask yourself a few concrete questions before forming any hypothesis:

- If you fired requests one at a time, sequentially, waiting for each
  response before sending the next, how would total throughput compare to
  firing them all at once with high concurrency? `bombard()` lets you try
  both (`concurrency=1` vs. `concurrency=30`, say) -- if concurrency barely
  helps, that itself is a huge clue about where the bottleneck lives.
- While a burst of concurrent requests is in flight, is the app process
  actually doing work in parallel, or does it look like it's handling one
  request completely before starting the next? You don't need a profiler to
  answer this -- a stopwatch and a print statement (or just watching how
  `p50` compares to `p95`/`p99` -- a huge gap between them is itself
  informative) will tell you a lot.
- Is the WORK each request does actually cheap, or does one request quietly
  do more round trips to somewhere else than it looks like from its
  response? A response with a handful of fields doesn't tell you how many
  queries it took to build.

You don't need to fix anything yet. The goal of this hint is just: don't
guess and change code. Reproduce the symptom on demand with `bombard()`,
and poke at it from a few different angles until you can describe, in one
sentence, what specifically gets worse as concurrency goes up. The next
hint gets more specific about where to look.
