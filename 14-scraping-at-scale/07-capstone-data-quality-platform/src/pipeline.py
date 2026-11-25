"""s13.t07 -- capstone: one data-quality platform pipeline recombining
everything the rest of this module built.

`run_pipeline(client_id, day=0, chaos=False, workdir=None)` is the single
entrypoint the validators call. Per real product id, it must:

  1. Discover every real product id via the paginated `/catalog` listing
     (task 01's concept) -- exclude every honeypot/trap link, never fetch
     one.
  2. Fetch `GET /product/{id}?day={day}` (cost `HTTP_COST`) and extract the
     seven HTML-visible fields with a real fallback chain across all 4
     markup versions (task 04's concept) -- `title`, `price`, `currency`,
     `in_stock`, `seller_name`, `review_count`, `description`.
  3. Run the extracted record through `quality_check()` (task 02's
     concept) and route it to a clean sink or a quarantine sink
     accordingly.
  4. Apply the budget router (task 05's concept): only if the extracted
     `review_count > 0`, ALSO fetch `GET /api/product/{id}?day={day}`
     (the ADDITIONAL `API_EXTRA_COST`) to fill in `rating`/`shipping_info`.
     A product with `review_count == 0` must never pay for that extra
     fetch.
  5. Instrument every fetch/quarantine/completeness/ban event through
     `src/metrics.py`'s `record_*`/`set_*` helpers (task 06's concept) --
     call `metrics.build_registry()` once at the start of this function.

Every request this function's crawl makes (discovery, html fetch, api
fetch) must go out under `X-Client-Id: {client_id}`, with a browser-like
`User-Agent`/`Accept-Language`, paced under the target's refill rate. On
this target request handling is sub-millisecond -- bounded concurrency
ALONE does not cap your throughput, you need an explicit dispatch-rate
pacer (measure real elapsed time, don't trust a single `sleep()` call's
requested duration; see tasks 01/05's READMEs and hints for the exact
gotcha). A full-catalog run here is roughly 4,000 html fetches plus
~1,200 render calls; paced sensibly it takes on the order of a couple of
minutes. `chaos=True` (forwarded as `?chaos=1` on every `/product/{id}`
request, never on `/api/product/{id}` -- chaos only affects markup
rendering, not the JSON endpoint's shape) makes the target cycle markup
version by wall-clock instead of by product id -- your extraction fallback
chain must not assume "this id defaults to version V," it must work from
the bytes alone, on every single response.

Nothing here is a database -- clean/quarantine output and a run summary
are written as plain files under `workdir` (default: a gitignored `run/`
directory next to this file; the caller may also pass its own `workdir`,
e.g. so CP1 and CP2 don't clobber each other's output).
"""

from pathlib import Path

HTTP_COST = 1.0        # GET /product/{id} -- paid for every product, every run
API_EXTRA_COST = 7.0    # the ADDITIONAL cost of also calling GET /api/product/{id}
RENDER_COST = HTTP_COST + API_EXTRA_COST
COMPLETENESS_TARGET = 0.98

DEFAULT_WORKDIR = Path(__file__).resolve().parents[1] / "run"

DEFECT_TYPES = (
    "missing_price",
    "price_na",
    "empty_title",
    "negative_price",
    "bad_currency",
    "truncated",
)


def discover_product_ids(client, day: int = 0, chaos: bool = False) -> list[int]:
    """Crawl the paginated `/catalog?page=&day=&chaos=` HTML listing and
    return the sorted list of REAL product ids, excluding every hidden
    honeypot/trap link (see task 01's `src/recon.py` docstring for exactly
    what those hiding signals look like -- `style="display:none"`,
    `class="hp"`, `rel="nofollow"`, and the page-1 `/trap/{token}` link).
    Following even one gets the client instantly banned.
    """
    raise NotImplementedError


def fetch_product_html(client, product_id: int, day: int = 0, chaos: bool = False) -> str:
    """GET /product/{id}?day={day}&chaos={1 if chaos else 0} -- the cheap
    html fetch. Return the raw response body text. Never call this for a
    honeypot id or anything under /trap/.
    """
    raise NotImplementedError


def extract_fields(html: str, product_id: int) -> dict:
    """Markup-resilient extraction (task 04's concept): parse `html` --
    ANY of the 4 markup versions, without being told in advance which one
    -- and return a dict with exactly these keys:

        title          str | None
        price          float | None
        currency       str | None
        in_stock       bool | None
        seller_name    str | None
        review_count   int | None
        description    str | None

    Build real fallback chains per field; a field genuinely absent from
    the page is `None`, never a guess. Do not extract `rating` or
    `shipping_info` here -- they are JS-only, never present in any markup
    version (see `fetch_product_detail`).

    This function is pure parsing -- no network I/O of its own.
    """
    raise NotImplementedError


def fetch_product_detail(client, product_id: int, day: int = 0) -> dict:
    """GET /api/product/{id}?day={day} -- the render step (the ADDITIONAL
    `API_EXTRA_COST` on top of the html fetch you already paid for this
    product). Return a dict with at least `rating` (float | None) and
    `shipping_info` ({"free", "eta_days", "carrier"} | None), with the
    volatile `_nonce` stripped. Only call this when the budget router (see
    `run_pipeline`) has decided this product needs it.
    """
    raise NotImplementedError


def quality_check(record: dict) -> tuple[bool, str | None]:
    """Data-quality contract (task 02's concept), applied to one extracted
    record (the dict `extract_fields` returns, plus `id`).

    Return `(is_clean, reason)`:
      - `(True, None)` if the record passes every rule below.
      - `(False, reason)` if it fails at least one -- `reason` is a
        human-readable string that MUST mention the name of the field the
        failing rule is about (e.g. "price is missing", "currency 'XYZ'
        not in allow-list") so a quarantine consumer knows what to look
        at. A record failing more than one rule still gets exactly one
        `reason` string (combine them, or pick one -- your choice).

    The six defect shapes to catch (same as task 02's contract, and the
    same six `DEFECT_TYPES` this module declares above -- ground your
    `reason` strings in that vocabulary):
      - `price` missing (key/value absent or `None`)
      - `price` non-numeric (e.g. the literal string "N/A")
      - `price` <= 0 (catches negative prices)
      - `currency` not one of a real ISO allow-list (USD/EUR/GBP/CAD)
      - `title` empty or blank after stripping whitespace
      - `description` carrying the truncation signal a corrupted record
        leaves behind (go look at a live defective record if you haven't
        already, e.g. via task 02 -- the literal marker is short and
        distinctive)

    Nothing here talks to the network or to pandera specifically -- how
    you implement the contract (a pandera schema reused from task 02, or
    plain Python) is your choice; the return shape above is the only hard
    requirement.
    """
    raise NotImplementedError


def run_pipeline(client_id: str, day: int = 0, chaos: bool = False, workdir=None) -> dict:
    """Top-level entrypoint. Crawl the full real catalog for `day` (under
    chaos markup cycling if `chaos=True`), extract every field, gate
    clean vs quarantine, apply the budget router, and write output under
    `workdir` (default `DEFAULT_WORKDIR`, created if it doesn't exist).

    For every real product id, in order:
      1. `discover_product_ids` once (not per-product) to get the full id
         list.
      2. `fetch_product_html` + `extract_fields` -- always.
      3. `quality_check` the extracted record -- route clean vs
         quarantine.
      4. If `review_count > 0` (from step 2's extraction, regardless of
         whether the record was clean or quarantined -- `review_count`
         itself is never the defective field), ALSO
         `fetch_product_detail` to fill in `rating`/`shipping_info`. A
         product that did NOT get rendered must have both left `None`.
      5. Call the appropriate `src/metrics.py` helper for every fetch,
         quarantine decision, and (at the end) set `spider_banned` and
         each tracked field's `spider_field_completeness`.

    Must not get the client banned over the course of a full run: browser-
    like headers on every request, honeypots/traps never touched, dispatch
    rate paced under the target's refill rate (bounded concurrency alone
    is not pacing on this target).

    Writes, under `workdir`:
      - `clean.jsonl` -- one JSON object per line, one per clean record:
        `{"id", "title", "price", "currency", "in_stock", "seller_name",
        "review_count", "description", "rating", "shipping_info"}`
        (`rating`/`shipping_info` are `None` unless this product was
        rendered).
      - `quarantine.jsonl` -- same shape, PLUS a `"reason"` key from
        `quality_check`.
      - `summary.json` -- the same dict this function returns (see below),
        serialized.

    Returns a dict:
        {
          "ids": [int, ...],          # every real product id processed, sorted
          "clean_count": int,
          "quarantine_count": int,
          "clean_path": str,
          "quarantine_path": str,
          "summary_path": str,
          "n_rendered": int,          # products where BOTH rating and shipping_info are populated
          "completeness": float,      # matched-required / total-required, required := review_count > 0
          "modeled_cost": float,      # len(ids)*HTTP_COST + n_rendered*API_EXTRA_COST
        }

    None of these numbers are self-graded truth -- every validator in this
    task recomputes them independently from `data/catalog.json` /
    `data/ground-truth.json` and the target's own `/__debug/client` state.
    This function's job is to make the pipeline actually correct, not to
    report a plausible-looking summary.
    """
    raise NotImplementedError
