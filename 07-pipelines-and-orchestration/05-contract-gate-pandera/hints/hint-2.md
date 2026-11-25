# Hint 2

The `scraped_at`-within-partition-day check needs the day (`dt`) as an input,
but a `DataFrameSchema`'s `Column`/`Check` objects are usually built once,
statically, with no per-call arguments. Two ways out: build the schema fresh
inside a function that takes `dt` as a parameter (a "schema factory"), or
validate that one rule separately from the rest of the pandera schema (e.g.
a plain pandas boolean mask) and fold its failures into the same
quarantine path. Either is fine; pick one and be consistent.

For `lazy=True`, catch `pandera.errors.SchemaErrors` and look at what's on
the exception object — specifically `.failure_cases`. It's a DataFrame with
one row per failed check per record; you'll need to figure out how to get
from "a bunch of check failures" back to "one quarantine row per invalid
input row, with a human-readable reason." Look at the `index` and `column`
values in `failure_cases` before writing any grouping logic.

For idempotency: the `UNIQUE (source_site, product_url, scraped_at)`
constraint on `core.price_records` means a straight `INSERT` with `ON
CONFLICT ... DO NOTHING` (or `DO UPDATE`) on that key handles reruns and the
"duplicate line in staging" case for free, without you tracking anything
yourself. For `ops.quarantine` there's no such constraint given — you either
add one, or delete-then-insert scoped to `dt` and `stage`, or dedupe some
other way before insert. Pick one deliberately.
