Concrete shapes for the two pieces most people get stuck on: the pacer, and
the overall discover-then-fetch pipeline. Still no ready-made code -- the
structure below is deliberately incomplete pseudocode, you fill in every
real line.

**A self-calibrating pacer.** The problem with `await asyncio.sleep(1 /
target_rate)` between dispatches is that the ACTUAL sleep duration you get
back doesn't reliably match the duration you asked for, especially at
short intervals. The fix is to stop trusting any individual `sleep()` call
and instead track a fractional "token" balance driven by REAL measured
elapsed time:

```
tokens = some starting value (e.g. 1)
last_check = perf_counter()
target_rate = requests per second you want to sustain

on each dispatch attempt:
    now = perf_counter()
    elapsed = now - last_check
    last_check = now
    tokens = min(some_cap, tokens + elapsed * target_rate)
    if tokens >= 1:
        tokens -= 1
        dispatch the request now
    else:
        sleep for a SHORT fixed amount (much shorter than 1/target_rate)
        and re-check tokens next loop iteration, rather than sleeping for
        the exact "correct" duration in one shot
```

The key idea: you're accumulating credit from time that has ACTUALLY
passed (measured, not requested), so it self-corrects regardless of the
OS's actual timer granularity. Pick `target_rate` comfortably below the
refill rate you observed during recon -- polite means leaving margin, not
skating exactly at the limit.

Wire this into your concurrency: a semaphore controls how many requests
are in flight at once, the pacer controls how often you're ALLOWED to
start a new one. Both together, not one or the other -- and the semaphore
alone will get you banned on this target, as hint-2 said.

**Discover-then-fetch pipeline.**

```
discover_product_ids(client, day):
    page = 1
    ids = set()
    loop:
        html = client.get("/catalog", params={"page": page, "day": day})
        parse html -> list of anchor tags
        for each anchor:
            if it matches ANY honeypot signal (display:none / class hp /
               rel=nofollow / href starting with /trap/): skip it, do not
               record it, do not fetch it
            else if it's a genuine /product/{id} link: extract id, add to
               ids
        if this page had zero genuine product links (or no "next" link):
            break
        page += 1
    return sorted(ids)

crawl_catalog(client_id, day):
    build client with the right default headers + X-Client-Id
    ids = discover_product_ids(client, day)
    results = []
    for each id in ids, paced (see pacer above), bounded concurrency:
        record = fetch_record(client, id, day)
        on 429: back off briefly, retry that one id
        results.append(record)
    return results
```

If you're using `asyncio`, the "for each id, paced, bounded concurrency"
step is naturally a set of worker tasks pulling from a shared queue of ids,
each one gated by the semaphore and the pacer before every dispatch --
that's the shape that lets you tune concurrency and rate independently.
Whatever shape you pick, verify it against `/__debug/client` yourself
(`harness.common.get_client_state`) DURING development on a small slice of
ids before ever attempting a full 4,000-product crawl -- confirming
`rate_limit_violations` stays near zero on 200 ids is a much cheaper
feedback loop than finding out you got banned after a minute-and-a-half
crawl.
