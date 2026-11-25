"""Single-node polars reimplementation of tasks 01-05's jobs, over the same
PriceWatch raw-events dump, checked against the same ground truth.

All functions are pure and take a `pathlib.Path` or `polars.LazyFrame` — no
SparkSession anywhere in this file. Build everything through the lazy API
(`pl.scan_ndjson`, `.lazy()` chains) so the query optimizer gets a chance to
push down filters/projections the way task 01 made you check for Spark.

Malformed-line gotcha (verified against polars==1.38.1, on this dataset):
`pl.scan_ndjson(...).collect()` and `pl.read_ndjson(..., ignore_errors=True)`
both raise `polars.exceptions.ComputeError: error parsing line: ...` on the
~3,000 syntactically-invalid lines in data/raw-events/*.jsonl (truncated
objects, `NOT_JSON ...` garbage). `ignore_errors` does NOT cover this case —
per its own docstring it only returns `Null` for *schema mismatches* (a
field that parses as JSON but doesn't match the inferred/declared column
type), not for lines that aren't valid JSON at all. Reducing `batch_size`
does not change this either (verified). There is no scan_ndjson keyword
that makes the reader skip unparseable lines and keep going — you have to
keep the malformed lines out before they reach the NDJSON parser.

Row-count expectations (2,000,000-row authoring scale, see
data/ground-truth.json):
    - valid JSON lines, duplicates included: total_rows_raw = 2,060,000
    - after removing exact whole-row duplicates:  distinct_rows = 2,000,000
    - malformed (unparseable) lines dropped:      malformed_line_count = 3,000
`load_events` must return a LazyFrame whose `.collect().height` is
2,000,000 — i.e. malformed lines dropped AND exact duplicates removed.

Dedup semantics, pinned from generate.py: a "duplicate" is a byte-identical
repeat of an earlier line (the generator literally re-inserts the same JSON
text at a random position to simulate a retried request). Dedup is
whole-row equality — every column, including the nested `attrs` struct —
not a dedup by some subset of columns.
"""

from pathlib import Path

import polars as pl


def load_events(jsonl_dir: Path) -> pl.LazyFrame:
    """Build a lazy frame of valid, deduplicated events from jsonl_dir/*.jsonl.

    Two things have to happen before this is safe to hand to the rest of
    the pipeline:
      1. Drop the ~0.15% of lines that are not valid JSON at all (see the
         module docstring above for what does and doesn't work here with
         polars 1.38.1 — you need to filter these out before they reach
         the NDJSON parser, not rely on a reader flag to skip them).
      2. Deduplicate exact whole-row repeats (every column must match,
         including the nested `attrs` struct).

    Returns:
        A `pl.LazyFrame` over the cleaned, deduplicated rows. Collecting
        it (`.collect().height`) must equal ground-truth.json's
        `distinct_rows`. Stay lazy here — do not `.collect()` inside this
        function only to wrap the result back in `.lazy()`; that defeats
        the point of the rest of the pipeline being able to push
        predicates/projections through your scan.
    """
    raise NotImplementedError("implement load_events")


def monthly_rollup(lf: pl.LazyFrame) -> dict:
    """Row count and price sum per calendar month, matching ground truth exactly.

    Month key: the first 7 characters of `captured_at` (an ISO-8601 UTC
    string, e.g. "2025-11-03T14:22:01Z"), i.e. "YYYY-MM".

    Per month:
      - rows: count of ALL deduplicated rows captured in that month,
        regardless of http_status (a 404/503 scrape attempt still counts
        as a row for that month).
      - price_sum: sum of `price` for rows in that month with
        `http_status == 200` only (price is null otherwise, by
        construction — see generate.py).

    Args:
        lf: the LazyFrame returned by load_events (already deduplicated).

    Returns:
        {
            "rows_by_month": {"2025-01": int, ..., "2026-06": int},
            "price_sum_by_month": {"2025-01": float, ..., "2026-06": float},
        }

    Must match ground-truth.json's rows_by_month / price_sum_by_month
    (price sums within a small floating-point tolerance).
    """
    raise NotImplementedError("implement monthly_rollup")


def filter_probe(lf: pl.LazyFrame) -> dict:
    """The ground-truth filter_probe slice: source_id == 4, captured_at in a date window.

    ground-truth.json's filter_probe was computed with:
        source_id == 4
        captured_at_from = "2025-09-01"
        captured_at_to   = "2025-10-31"  (inclusive)

    Read as a half-open range on the ISO string: captured_at >= "2025-09-01"
    and captured_at < "2025-11-01" (the day after the inclusive end date).
    String comparison works correctly here because captured_at is a
    zero-padded ISO-8601 UTC string.

    Args:
        lf: the LazyFrame returned by load_events (already deduplicated).

    Returns:
        {
            "rows": int,        # count of matching rows, any http_status
            "price_sum": float, # sum(price) over matching rows with
                                 # http_status == 200 only
        }

    Must match ground-truth.json's filter_probe.rows / filter_probe.price_sum.
    """
    raise NotImplementedError("implement filter_probe")


def top3_per_source(lf: pl.LazyFrame) -> dict:
    """Top-3 prices per source_id, matching ground truth's top_n_per_source.

    Restrict to http_status == 200 rows (price is null otherwise). Rank by
    price descending; ties are broken by product_id descending (this is
    ground-truth.json's own documented tie rule — see
    top_n_per_source.note). Take the top 3 per source_id.

    Args:
        lf: the LazyFrame returned by load_events (already deduplicated).

    Returns:
        {
            "1": [{"price": float, "product_id": int}, ...],  # length 3
            "2": [...],
            ...
            "20": [...],
        }
        Each source's list must be in descending rank order (best price
        first), matching ground-truth.json's top_n_per_source.by_source
        exactly, element for element.
    """
    raise NotImplementedError("implement top3_per_source")
