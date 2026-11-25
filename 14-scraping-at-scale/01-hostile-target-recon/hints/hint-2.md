Four specific mechanisms, one per defense.

**Header gate.** The target checks two headers on every non-debug request:
`User-Agent` must CONTAIN the substring `Mozilla/5.0` (it doesn't have to
be a real Chrome/Firefox UA string, just contain that token), and
`Accept-Language` must be present and non-blank. Set both once when you
build your client (however you're constructing it -- a configured
`httpx.Client`/`httpx.AsyncClient`, or a small wrapper around one) so every
request automatically carries them, rather than remembering to add them
per call. Also attach a consistent `X-Client-Id` header (the value passed
into `crawl_catalog`) to every request -- that's what ties all of your
requests together into one rate-limit bucket and one `/__debug/client`
record, both for you and for the validator.

**Honeypots.** In the `/catalog` listing HTML, a real product link and a
trap link are both plain `<a href="...">` tags -- the only difference is
in the surrounding attributes. Treat ANY of these as a hard signal to skip
a link, not follow it: an inline `style` containing `display:none`, a
`class` containing `hp`, a `rel="nofollow"`, or an `href` starting with
`/trap/`. Don't try to special-case exact string matches on one attribute
-- check for all of the signals, since any one of them alone marks a trap.
This is a parsing problem: pick an HTML parser (this module has `parsel`,
`lxml`, `beautifulsoup4`, and `selectolax` available) and select on tag
attributes, don't regex the raw markup.

**Rate limiting.** Bounded concurrency (a semaphore capping how many
requests are in flight at once) is not the same thing as a rate limit, and
on this particular target the two are NOT interchangeable -- request
handling is fast enough that a concurrency cap alone still lets you fire
requests much faster than the target's refill rate allows, and you'll get
banned. You need an explicit control on how often you DISPATCH a new
request, independent of how many are in flight. A fixed
`await asyncio.sleep(interval)` between dispatches sounds like it should
work but is unreliable for short intervals on Windows specifically (the
default timer resolution quantizes short sleeps to coarse ticks) -- the
next hint gets concrete about a pacing approach that sidesteps that. As a
safety net (not your primary strategy), handle a `429` response by backing
off before retrying rather than immediately hammering again -- but a
well-paced client should see very few of these, not rely on them.

**JS-only fields.** `GET /api/product/{id}?day=` returns a JSON body with
every field the HTML page has, PLUS `rating` and `shipping_info`. Decide
in `fetch_record` whether you need the HTML page at all, or whether the
API response alone gives you everything `fetch_record`'s docstring asks
for -- check what fields are actually in that JSON body before assuming
you need two requests per product.
