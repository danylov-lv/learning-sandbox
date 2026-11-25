# 01 -- Hostile-target recon

## Backstory

Your team needs a clean export of a competitor's product catalog for a
pricing study. Someone already tried the obvious thing -- a `for` loop over
product ids hitting `GET /product/{id}` as fast as `requests` would go --
and it lasted about two seconds before every request started coming back
403. Whoever wrote it never even noticed the two suspicious links buried in
every listing page that don't look like the others.

This task is the "figure out what you're dealing with, then build a client
that behaves" step that comes before literally any large scrape against a
site that isn't friendly to you. You are not exploiting a vulnerability --
the target's defenses (a header check, hidden trap links, a rate limiter
that bans on abuse) are exactly what a real e-commerce site runs to keep
scrapers off its infrastructure, and the honest way through them is the
same thing a legitimate crawler does: identify yourself like a real
browser, don't touch what you're not supposed to touch, and don't hammer
the server. Get all three wrong and you're banned before you've pulled a
tenth of the catalog.

## What's given

- The target site, already running via the module's `docker-compose.yml`
  at `http://localhost:8313` (or whatever `SANDBOX_13_TARGET_PORT`
  resolves to -- `harness.common.target_base_url()` gives you the right
  URL either way). ~4,000 real products, id-ordered, behind a paginated
  `/catalog` listing.
- `src/recon.py` -- three functions, each `raise NotImplementedError` with
  a docstring spelling out its exact contract: `discover_product_ids`,
  `fetch_record`, and the top-level `crawl_catalog` the validator actually
  calls.
- `RECON.md` -- an unfilled writeup template (4 sections) you complete
  after building the client, describing each defense you found and how you
  handled it.
- `harness/common.py` -- `target_base_url()` / `target_port()`, plus
  `get_client_state(client_id)` / `reset_client(client_id)` (talk to the
  target's `/__debug/*` endpoints so you and the validator can inspect a
  client's request/ban/violation counters). `TargetClient` there is a
  minimal example of a browser-like `httpx.Client` (default `User-Agent`/
  `Accept-Language`/`X-Client-Id`) meant for validators poking the
  target -- it does no parsing, retrying, pacing, or honeypot avoidance.
  **You write your own fetch layer for this task**; nothing in `harness/`
  does that for you, on purpose.
- `hints/` if you get stuck, ordered from a nudge to something close to
  pseudocode.

## What's required

Implement all three functions in `src/recon.py` (see each docstring for
the exact contract):

- `discover_product_ids(client, day=0) -> list[int]` -- crawl the
  paginated `/catalog` HTML listing, parse the real product links, and
  exclude every hidden honeypot/trap link. Return the sorted list of real
  product ids.
- `fetch_record(client, product_id, day=0) -> dict` -- fetch one product's
  full structured record, including the two fields (`rating`,
  `shipping_info`) that only exist behind `GET /api/product/{id}`.
- `crawl_catalog(client_id, day=0) -> list[dict]` -- the top-level
  entrypoint. Build a polite, header-correct, honeypot-avoiding,
  rate-limit-respecting client identified by `X-Client-Id: {client_id}`,
  discover every real id, fetch every record, and return the list. Must
  not get the client banned.

Then fill in `RECON.md`, describing what you actually found: the header
gate, the rate limit's shape and how you paced around it, where the
honeypots hide and how you told them apart from real links, and where the
JS-only fields live.

A polite full-catalog crawl on this target takes on the order of a minute
and a half at a sane pace -- that is expected and correct, not a bug to
optimize away. A crawl that finishes in two seconds either skipped most of
the catalog or is about to get banned.

## Completion criteria

Run from the **module root** (not this task directory):

```bash
uv run python 01-hostile-target-recon/tests/validate.py
```

The validator resets a fresh client id, calls your `crawl_catalog` exactly
once, and checks (against an oracle it computes itself from
`data/ground-truth.json` / `data/catalog.json` and the target's own
`/__debug/client` state -- never trusting your output as truth):

- the returned ids are EXACTLY the real product id set (right count, no
  duplicates, no honeypot ids);
- your client ended the crawl with `banned=False`, `honeypot_hits=0`,
  `header_rejections=0`, and a small enough `rate_limit_violations` count
  (a handful of 429s recovered via backoff is fine; a ban is not);
- a spread sample of records matches the catalog oracle field-for-field
  (title/price/currency/in_stock/review_count), with `rating` and
  `shipping_info` populated wherever `review_count > 0` -- proof you
  actually called the JS-only endpoint, not just the HTML page;
- `RECON.md` is filled in (no leftover `[fill in` placeholders, every
  section has real content).

It prints `PASSED` with a summary, or `NOT PASSED: <reason>` and exits 1.

## Estimated evenings

2

## Topics to read up on

- `robots.txt` conventions and why real crawlers respect `Disallow`
- HTTP header-based client fingerprinting (`User-Agent`, `Accept-Language`)
- Honeypot/trap links in scraped HTML (hidden via CSS, `rel="nofollow"`)
- Token-bucket rate limiting (capacity, refill rate, burst vs. sustained
  rate)
- Bounded concurrency vs. explicit dispatch-rate pacing (why a semaphore
  alone doesn't cap throughput against a fast target)
- `asyncio` event-loop timer resolution and self-calibrating pacers
  (measuring real elapsed time instead of trusting a single `sleep()`
  call)
- `429 Too Many Requests` / `Retry-After` and backoff as a safety net
  (not a primary rate-control strategy)
- XHR/"headless render" endpoints as a source of JS-populated fields

## Off-limits

`.authoring/design.md` (module root) documents this target's entire
defense implementation and the harness API contract -- spoilers, don't
read it before finishing this task.

`data/target-spec.json` and `data/catalog.json` are the target's OWN
backend config and product data (rate-limit thresholds, honeypot ids,
markup-version assignment, bad-record ids). Reading either one directly
trivializes this task -- everything you need to build `src/recon.py` you
learn by making requests against the running target and reading its
responses, the same way you would against a real site you don't control.
