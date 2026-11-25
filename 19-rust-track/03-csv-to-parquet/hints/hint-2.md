## `looks_like_timestamp`

Work on `s.as_bytes()`, not `&str` indexing (byte indexing is cheaper here
and you're only ever comparing against ASCII bytes). First check the
length is exactly 20 -- that alone rejects `"not-a-date"` and any
truncated or extended garbage before you look at a single character.
Then check the four fixed-position separator bytes (`b'-'`, `b'-'`,
`b'T'`, `b':'`, `b':'`, `b'Z'`) are exactly where the format says, and
that every other position is `u8::is_ascii_digit()`. A small closure or a
loop over `(range, expected_byte)` pairs keeps this from turning into ten
near-identical `if` statements.

## `parse_row`

Once you have your 6 fields as `&str` slices: parse `id` first with `?`
(so a broken id short-circuits immediately, matching the field order in
the file). Check `sku` is non-empty before you allocate a `String` for
it -- there's no point converting an empty slice into an empty `String`
just to check `.is_empty()` again afterward. Parse `price` with `?`, then
check positivity as a *separate* step -- the float-parse failure and the
"parsed fine but non-positive" failure are two different `RowParseError`
variants for a reason (an empty field and a `-14.08` field are different
bugs to a human debugging this later). `in_stock` is a plain three-way
`match` on the exact strings `"true"`/`"false"`/anything else -- no
`bool::from_str` or similar, since that would accept things like `"TRUE"`
this format never produces and this task doesn't need to think about.

## `parse_rows`

`reader.lines()` already gives you almost everything: an iterator of
`io::Result<String>`. You need `Result<ProductRow, RowParseError>`
instead. Two `.map()` calls back to back get you there: one that unwraps
the `io::Result` (a read failure on a file you just opened is not
something this task asks you to model as a `RowParseError` -- `.expect()`
is fine), one that calls `parse_row` on the resulting `String`. Resist
the urge to `.collect::<Vec<_>>()` in the middle -- the whole reason this
function's signature returns `impl Iterator` instead of `Vec<...>` is so
the 500k-row file streams through one line at a time.

## `build_column`

`T::Builder::default()` gets you an empty builder without needing to know
anything about its constructor. The loop is: for each `value: T` in
`values`, call `T::append(&mut builder, &value)`. `ArrayBuilder::finish`
(a trait method every concrete builder implements) hands back an
`ArrayRef` directly -- you don't need to wrap it in `Arc::new` yourself,
`finish`'s return type already is `ArrayRef`. Pair that with
`Field::new(name, T::arrow_data_type(), false)` and you have your tuple.

## `write_products_parquet`

Six `Vec<_>` accumulators (one per `ProductRow` field), filled by
matching on each `parse_rows` result: `Ok(row)` pushes one value onto each
of the six vecs and bumps `valid_rows`; `Err(_)` just bumps `dirty_rows`
(the specific error doesn't matter to this function -- it already did its
job by making the row not-`Ok`). `total_rows` is every line seen,
regardless of outcome. Once you have six full vecs, six calls to
`build_column` give you six `(Field, ArrayRef)` pairs -- split those into
a `Vec<Field>` (for the `Schema`) and a `Vec<ArrayRef>` (for
`RecordBatch::try_new`). Wrap the schema in `Arc` once, and reuse that
same `Arc` for both `RecordBatch::try_new` and `ArrowWriter::try_new` --
they both want a `SchemaRef`, i.e. `Arc<Schema>`.
