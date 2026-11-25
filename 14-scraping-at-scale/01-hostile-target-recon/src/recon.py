"""s13.t01 -- hostile-target recon: a polite, defense-aware catalog crawler.

Three functions to fill in. Nothing in `harness/` writes your fetch layer
for you -- you build the client here: browser-like headers so the target's
header gate lets you through, honeypot/trap-link avoidance while parsing the
listing HTML, and an explicit dispatch-rate pacer so the token-bucket rate
limiter never bans you. See this task's README for the contract the
validator checks, and `hints/` if you get stuck.

The two JS-only fields (`rating`, `shipping_info`) never appear in the HTML
detail page under any markup version -- they only exist in the JSON body of
`GET /api/product/{id}` (the "headless render" stand-in). `fetch_record`
must return them, so it has to call that endpoint.

`harness.common` gives you `target_base_url()` (respects
`SANDBOX_13_TARGET_PORT`) and the browser-like `DEFAULT_USER_AGENT` /
`DEFAULT_ACCEPT_LANGUAGE` constants. You choose the HTTP client (`httpx` is
already a dependency); just remember to set `X-Client-Id: {client_id}` on
every request so the target scopes its per-client rate-limit/ban state to
your run (and the validator can read it back via `/__debug/client`).
"""


def discover_product_ids(client, day: int = 0) -> list[int]:
    """Crawl the paginated `/catalog?page=&day=` HTML listing and return the
    sorted list of REAL product ids.

    Each listing page mixes real `<a href="/product/{id}">` links with hidden
    honeypot/trap links (some `style="display:none"`, some `class="hp"`, some
    `rel="nofollow"`, plus a `/trap/{token}` link on page 1). You must EXCLUDE
    every hidden/trap link -- following even one gets the client instantly
    banned. Real product links look like ordinary anchors; the trap ones
    carry one of those hiding signals. `robots.txt` also disallows `/trap/`.

    `client` is whatever HTTP client you built (it must already send the
    browser-like headers and `X-Client-Id`). Paginate until there are no more
    pages. Return the ids sorted ascending, no duplicates, no honeypot ids.
    """
    raise NotImplementedError


def fetch_record(client, product_id: int, day: int = 0) -> dict:
    """Fetch one product's FULL structured record, including the two JS-only
    fields (`rating`, `shipping_info`) that are absent from the HTML detail
    page and only present in `GET /api/product/{id}?day={day}`.

    Return a dict with at least the product's `id`, `title`, `price`,
    `currency`, `in_stock`, `review_count`, and -- from the API endpoint --
    `rating` and `shipping_info` ({"free","eta_days","carrier"}). Strip the
    per-request `_nonce` (it's fresh noise on every response and means
    nothing). `rating` is legitimately `null` when `review_count == 0`.
    """
    raise NotImplementedError


def crawl_catalog(client_id: str, day: int = 0) -> list[dict]:
    """Top-level entrypoint the validator calls. Build a polite,
    header-correct, honeypot-avoiding, rate-limit-respecting client
    identified by `X-Client-Id: {client_id}`, discover every real product id,
    fetch every record (with the JS-only fields), and return the list.

    The client must finish UNBANNED with zero honeypot hits, zero header
    rejections, and only a handful of recovered 429s at most. On this target,
    request handling is sub-millisecond, so bounded concurrency ALONE does
    not cap your throughput -- you need an explicit dispatch-rate pacer that
    stays under the target's refill rate (measure real elapsed time; do not
    trust a single `sleep()` call's requested duration). A full polite sweep
    of ~4,000 products takes on the order of a minute and a half -- that is
    expected, not a bug to optimize away.

    Return a list of record dicts (as from `fetch_record`), one per real
    product id.
    """
    raise NotImplementedError
