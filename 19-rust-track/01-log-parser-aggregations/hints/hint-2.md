# Hint 2

**Finding the delimited sections.** `str::find` and `str::rfind` locate a
byte offset; string slicing (`&line[a..b]`) is how you turn two offsets
into a borrowed field. The timestamp is bounded by the first `[` and the
first `]` after it. The request line and the user-agent are both bounded
by `"` characters -- there are exactly two quoted sections in a
well-formed line, so finding the first pair of quotes and then the second
pair (searching from where the first pair ended) locates both without
guessing. Everything else is separated by plain ASCII spaces, so
`str::split_whitespace` or `str::split(' ')` handles it once you've carved
out the quoted/bracketed chunks.

**The request line.** Once you have the text between the first pair of
quotes (`"GET /api/products HTTP/1.1"` minus the quotes), it's three
space-separated tokens: method, path, and an HTTP version you can ignore.
Splitting that inner string on whitespace and taking the first two pieces
gives you `method` and `path` directly, both still borrowed from the
original line.

**Turning a missing piece into an error, not a panic.** Every `str::find`
/ `.next()` on a splitter returns an `Option`. `.ok_or(LogParseError::
MissingField("..."))?` is the idiom that turns "this delimiter wasn't
there" into a propagated `Err` in one line, instead of an `.unwrap()` that
would panic on the first corrupted line in a 200,000-line file.

**Numbers.** `status_str.parse::<u16>()?` and `bytes_str.parse::<u64>()?`
rely on the `From<ParseIntError>` conversion you're filling in on
`LogParseError` -- that's the whole reason `?` can jump straight from a
`ParseIntError` to your enum without an explicit `.map_err(...)`.
`response_time_str.trim().parse::<f64>()?` needs the `ParseFloatError`
conversion the same way. Watch for trailing whitespace/newline on the
final field -- trim it before parsing.

**Aggregating.** `HashMap`'s `entry(key).or_insert(0)` (or `or_default()`)
is the one-line idiom for "increment this bucket, creating it at 0 if it's
new" -- you want this, not a `if map.contains_key(...) { ... } else { ...
}` branch. `BufRead::lines()` gives you an iterator of `io::Result<String>`
one line at a time without ever holding the whole file in memory;
`.filter_map(...)` or a plain loop with a `match` on `parse_line`'s result
both work for routing well-formed vs malformed lines into the right
counters.

**Percentile.** The formula is spelled out exactly in the doc comment on
`percentile` -- sort once (`f64` doesn't implement `Ord` because of `NaN`,
so you'll reach for `.sort_by(|a, b| a.partial_cmp(b).unwrap())` or
`f64::total_cmp`), then it's index arithmetic, no loop needed.
