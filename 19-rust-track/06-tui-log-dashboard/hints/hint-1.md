# Hint 1

Build this in three separable layers, and don't move to the next one
until the previous one's tests are green: `parse_log_line` (a pure
string -> `Option<ParsedLine>` function, no `App` involved at all), then
`App::handle_event` (pure state transitions, no rendering involved), then
`render` (reads `App`, draws widgets, never mutates anything). Each layer
has its own test file for a reason -- `tests/parse_log_line.rs` never
touches `App`, `tests/app_event_handling.rs` never touches `ratatui`, and
only `tests/render_test_backend.rs` needs a `Terminal`/`TestBackend` at
all. If you're stuck on a `render_test_backend.rs` failure, make sure
`app_event_handling.rs` is fully green first -- a rendering bug is much
easier to find once you're sure the state it's drawing is correct.

**`parse_log_line`** is the same kind of problem as module 01's
`parse_line`, scoped down: you only need three fields (method, path,
status), not the whole record. Find the quoted section, split it into
tokens, validate the path looks like a path, then parse the status. Don't
try to handle every corruption mode as a special case -- write the happy
path and let a missing token or a failed `.parse()` naturally produce
`None` via `?`'s early-return behavior on `Option` (the `?` operator works
on `Option`-returning functions too, not just `Result`-returning ones).

**`App::handle_event`** is an exhaustive `match` over 4 variants, and the
module doc comment at the top of `src/lib.rs` spells out exactly which
fields each variant is allowed to touch. Write the `match` arms one at a
time, and after each one, ask: "does this arm touch any field the module
docs didn't say it should?" That question alone catches most of the bugs
this task's tests are built to catch (see `tests/app_event_handling.rs`'s
`*_only_*` tests).

**`render`** is where you'll spend time on the `ratatui` API itself rather
than on logic. Skim `ratatui`'s own docs/examples for `Layout`,
`Constraint`, `Block`, `Paragraph`, and `List` before writing this
function -- the shapes involved (a vertical layout, then a horizontal
split for two side-by-side panes) are one of the most common patterns in
any `ratatui` app, not something specific to this task.

Don't design your own ring-buffer type -- `std::collections::VecDeque`
already has `push_back`/`pop_front` in O(1), which is exactly a ring
buffer's two operations.
