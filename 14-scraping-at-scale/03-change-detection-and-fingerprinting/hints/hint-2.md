`GET /product/{id}` renders one of 4 markup versions depending on
`1 + (product_id % 4)` (no `?v=` needed to see all of them -- a plain crawl
over many ids already hits every version). Each one embeds the same kind of
volatile marker, but encoded differently -- go look at the actual HTML for
a handful of ids spanning all four `id % 4` remainders and find it in each:
a `<meta>` tag, an HTML comment, a hidden `<span>`, and a key inside a JSON
`<script>` block. `GET /api/product/{id}` has its own version of the same
thing, as a top-level JSON key. None of the four HTML forms and the one JSON
form look alike -- there is no single regex or CSS selector that catches
all five in one shot; you need to know which markup version (or which
endpoint) you're looking at before you know which trick removes its marker.

Two directions that both work, pick one and be consistent:

- **Normalize the raw response.** Strip (or blank out) every one of those
  five volatile-marker shapes from the raw text BEFORE hashing anything
  else. This only requires recognizing the marker's shape per version/
  endpoint, not parsing the rest of the page -- simpler, but only correct if
  you are confident you've found and neutralized every volatile position
  (miss one and the negative control in the validator will catch it).
- **Extract, then hash a canonical structure.** Parse out just the fields
  you actually care about (price, currency, in_stock, title, description,
  review_count, ...) into a plain dict/tuple, deliberately never touching
  the nonce field at all, and hash a canonical serialization of THAT. This
  sidesteps the "did I strip every marker shape" risk entirely, at the cost
  of needing a per-markup-version extraction step (the same kind of problem
  task 04 digs into in more depth).

Either way, `fingerprint()`'s docstring asks you to pick and document which
shape you're feeding it (`payload`) -- decide that up front, since
`build_fingerprint_index`/`changed_between` in `detect.py` are the ones that
actually fetch and must hand `fingerprint()` a matching shape.

Whatever "state between days" means for your `changed_between`, you don't
have to re-derive it from scratch on every call: `build_fingerprint_index`
is exactly the "per-day index" a real incremental scraper would persist
(e.g. to a JSON file under this task's gitignored `run/` dir) and diff
against on the next run, instead of always re-fetching both days from
scratch.
