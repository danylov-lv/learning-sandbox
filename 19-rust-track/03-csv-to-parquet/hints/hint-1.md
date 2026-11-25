This task is three separate, smaller problems stacked on top of each
other: "turn one line of text into a `ProductRow` or reject it",
"turn a column of Rust values into an arrow array", and "wire a
`RecordBatch` into a Parquet file on disk." Get the first one solid on
its own -- `parse_row` doesn't need arrow or parquet at all, and
`tests/parse_row.rs` will tell you the moment it's right, well before you
touch a `RecordBatch`.

For `parse_row`: you already wrote almost exactly this shape of function
in task 01 (`parse_line`), just with a different error enum and a
different set of fields. `line.split(',')` gives you an iterator of `&str`
slices; collect it, check the length, then read off each field by index.
Reach for `?` on every `.parse()` call the same way task 01 did -- that's
what the `From<ParseIntError>` / `From<ParseFloatError>` impls on
`RowParseError` are already there for.

For `build_column`: look at what `ArrowColumn` promises before you write
anything -- an associated `Builder` type, a way to get the right
`DataType`, and a way to push one value into that builder. Given those
three things, the function that builds a whole column looks exactly like
"make an empty builder, loop and push, then finish" no matter which
concrete Rust type you're building a column of. If you find yourself
writing `match` on the type of `T` inside `build_column`, that's a sign
you're fighting the generic instead of using it -- the whole point of
`ArrowColumn` is that `build_column` never needs to know or care which
concrete type it's working with.

For `write_products_parquet`: get a `RecordBatch` built and printed with
`println!("{batch:?}")` (or just inspect its `num_rows()`/`schema()`)
before you touch `ArrowWriter` at all. Once you're confident the batch
itself is right, writing it to a file is three or four calls in a row,
not a design problem.

Don't reach for the `csv` crate -- it isn't a dependency of this task on
purpose (every field in the real data is comma-free, so a hand-rolled
split is exact and simpler than a general CSV parser would be).
