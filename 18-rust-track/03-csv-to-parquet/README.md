# 03 -- CSV to Parquet

## Backstory

The scraper pipeline from task 01 has a sibling: instead of a web server's
access log, this one's `data/products.csv` is a nightly product-catalog
scrape -- half a million rows, one per SKU, refreshed every night. Nobody
downstream wants to open a 500k-row CSV in anything ever again. They want
a Parquet file: columnar, typed, compressed, and readable by every
analytics tool in the building without anyone re-parsing text. Your job
is the one-time (well, nightly) conversion step in between: read the raw
scrape, throw out the rows the scraper itself got wrong, and write
everything else out with a real schema.

This is also where two Rust ideas that task 01 didn't need show up for
real: a trait with an associated type is how you write "the same
column-building logic" once and have it work for an `i64` column, a
`String` column, and a `bool` column without three copies of nearly
identical code: and a custom error type now has to absorb failures from
two crates that were never designed to know about each other (a hand-rolled
row parser and `arrow`'s own error type), which is exactly what `From`
conversions and `?` are for.

## What's given

- `src/lib.rs` -- a scaffold: `ProductRow` and `RowParseError` (fully
  defined, not stubs -- these are the shared vocabulary your code and the
  tests both speak), the `ArrowColumn` trait with its four impls
  (`i64`/`f64`/`bool`/`String`, also fully defined -- these are
  intentionally-boring plumbing, not the interesting part of this task),
  and `PipelineError`/`ConversionStats` (also fully defined). Four
  functions have `todo!()` bodies for you to fill in: `looks_like_timestamp`,
  `parse_row`, `parse_rows`, `build_column`, and `write_products_parquet`.
- `sandbox18_harness::ground_truth` (a dependency, not something you
  write): `data_path("products.csv")` and `load().csv` for locating the
  real CSV and its precomputed answer key.
- `data/products.csv` and `data/ground-truth.json` at the module root, via
  `cargo run -p sandbox18-datagen` (run it first if `data/` is empty --
  see the module README).
- `tests/` -- the validator. Every test's assertions carry an explanatory
  message.

## What's required

Implement the five `todo!()` pieces in `src/lib.rs`:

1. **`looks_like_timestamp`** -- a small structural check (see "The
   `scraped_at` field" below).
2. **`parse_row`** -- turns one CSV data line into a `ProductRow`, or the
   first `RowParseError` that applies (see "Dirty rows" below for exactly
   which lines must be rejected).
3. **`parse_rows`** -- streams a `BufRead` through `parse_row`, one line
   at a time, as an `impl Iterator` -- never collecting the whole file
   into a `Vec` first.
4. **`build_column`** -- one generic function, `T: ArrowColumn`, that
   turns any `Iterator<Item = T>` into an arrow `(Field, ArrayRef)` pair
   by driving `T::Builder`.
5. **`write_products_parquet`** -- the end-to-end pipeline: open the CSV,
   skip its header, parse every remaining line, keep only the valid rows,
   build all six columns via `build_column`, and write them out as one
   Parquet file with `parquet::arrow::ArrowWriter`.

### The CSV format

`data/products.csv` has one header line, then one data line per product:

```text
id,sku,category,price,in_stock,scraped_at
1,SPO-0000001,Sports,38.87,true,2024-01-08T12:35:55Z
```

No field ever contains a comma or a quote in this data set (category
names like `"Home & Garden"` have a space and an `&`, never a comma), so
`line.split(',')` is exact -- there is no need for a `csv`-parsing crate
or for quote-aware splitting, and none is on this task's dependency list.

### Dirty rows

About 2% of data lines are corrupted, one way per line, across six
independent modes:

- `price` is empty (`...,,true,...`)
- `price` is the literal text `N/A`
- `price` parses as a number but is `<= 0` (a negative price)
- `sku` is empty (`...,,Electronics,...`)
- `in_stock` is neither `true` nor `false` (e.g. `maybe`)
- `scraped_at` doesn't match `YYYY-MM-DDTHH:MM:SSZ` (e.g. `not-a-date`)

`parse_row` must reject all six as `Err`, never panic, and never
substitute a best-guess value. `id` and `category` are never corrupted in
the real data, but `parse_row` should still handle a line with the wrong
number of fields defensively (`RowParseError::WrongFieldCount`).

### The `scraped_at` field

This task does not parse `scraped_at` into any kind of timestamp type --
it's stored as-is, `String`, in `ProductRow`. `looks_like_timestamp` only
needs to confirm the fixed shape `YYYY-MM-DDTHH:MM:SSZ`: 20 bytes, digits
everywhere except literal `-` at offsets 4 and 7, `T` at offset 10, `:`
at offsets 13 and 16, and `Z` at offset 19. You do not need to validate
that the date is a real calendar date (no February 30th check) -- the
one corrupted shape this task's data actually contains is the literal
text `not-a-date`, which fails this structural check immediately.

### The header line

`write_products_parquet` is the only place that knows `data/products.csv`
has a header -- it must skip exactly the first line, unconditionally,
before handing the rest to `parse_rows`. `parse_row` and `parse_rows`
never see a header and never try to detect one.

### The Parquet schema

In this exact column order, none nullable:

| column       | arrow `DataType` |
|--------------|------------------|
| `id`         | `Int64`          |
| `sku`        | `Utf8`           |
| `category`   | `Utf8`           |
| `price`      | `Float64`        |
| `in_stock`   | `Boolean`        |
| `scraped_at` | `Utf8`           |

Compress with `parquet::basic::Compression::SNAPPY`, and cap each row
group at `row_group_size` rows (the parameter `write_products_parquet`
takes) via `WriterProperties::builder().set_max_row_group_row_count(...)`.

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t03-csv-to-parquet
```

All given tests pass. They cover, at minimum:

- `parse_row` accepts a well-formed line and rejects each of the six
  dirty-row corruption modes with the right `RowParseError` variant.
- A small, hand-built CSV (two categories, several dirty rows of
  different kinds) round-trips through `write_products_parquet` and back
  through a real Parquet reader: dirty rows are excluded, row counts and
  per-category price statistics come out exactly as hand-computed, and
  the written schema's column types match the table above.
- The real `data/products.csv`, converted and read back, matches
  `data/ground-truth.json` on row counts, per-category and overall price
  statistics (mean/sum within a small money tolerance, min/max tighter),
  and the in-stock/out-of-stock split.

If you're unsure whether an implementation is "done enough": the tests
check more than one category with different statistics, so a writer that
collapses every row into one category or reports the same numbers
regardless of category fails immediately, even if row counts happen to
look right.

## Estimated evenings

2-3

## Topics to read up on

- Associated types on a trait (`type Builder`) vs. a plain generic
  parameter -- why "one builder type per implementation" is the right
  shape here
- `arrow`'s `ArrayBuilder` trait and the concrete builders
  (`Int64Builder`, `Float64Builder`, `BooleanBuilder`, `StringBuilder`) --
  what `append_value` and `finish` do on each
- `RecordBatch` and `Schema`: how a set of `(Field, ArrayRef)` pairs
  becomes one typed, columnar batch
- `impl Trait` in return position -- what "opaque type" means here, and
  why a function returning `impl Iterator<...>` can change its internal
  implementation without changing its signature
- `parquet::arrow::ArrowWriter` and `WriterProperties` -- compression
  codecs and row-group sizing, and why row-group size is a write-time
  choice that affects how a reader can later parallelize or skip data
- Custom error types spanning multiple crates: implementing `From` for
  each upstream error type your code can produce, so `?` works uniformly
  across a hand-rolled parser, `arrow::error::ArrowError`, and
  `parquet::errors::ParquetError`
- Reading a large file with `BufRead::lines()` as a lazy iterator instead
  of `std::fs::read_to_string`, and why that matters at 500k rows

## Off-limits

`.authoring/design.md` (at the module root) documents this task's grading
internals -- read it after you're done, if at all, not before.
