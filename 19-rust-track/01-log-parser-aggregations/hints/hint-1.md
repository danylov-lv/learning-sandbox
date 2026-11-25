# Hint 1

Start from the shape of one line, not the shape of the whole file. Get
`parse_line` solid on a single `&str` first -- `aggregate` is then "call
`parse_line` once per line and fold the results," which is a much smaller
problem once parsing is done.

Read the line format described at the top of `src/lib.rs` slowly. Every
field is either delimited by a fixed character (`[`/`]`, `"`/`"`, a space)
or sits in a fixed position relative to one of those delimiters. You don't
need a general-purpose parser or a regex crate (there isn't one on this
module's dependency list anyway) -- you need to walk the string using the
handful of `&str` methods that find a delimiter and split around it.

Think about ownership before you write anything: `parse_line` takes `&str`
and must return a `LogEntry<'a>` whose fields borrow from that same `&str`.
Every method that slices a string without copying it (the ones that return
`&str`, not `String`) keeps you inside that contract. The moment you find
yourself reaching for `.to_string()` or `.to_owned()` on a field you're
about to put into `LogEntry`, stop -- that's a sign you're fighting the
type signature instead of using it.

For the error side: don't try to anticipate every corruption mode
individually. Write the *happy path* first, field by field, and let each
step fail naturally (a missing delimiter, a `.parse()` that returns `Err`)
propagate out with `?`. A parser written to expect the well-formed shape,
with no special-casing for what's "supposed" to go wrong, catches
malformed input as a side effect of correctly requiring the well-formed
shape.
