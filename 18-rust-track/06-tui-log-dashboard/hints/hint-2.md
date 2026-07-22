# Hint 2

## `parse_log_line`

`line.find('"')` gives you the byte offset of the first quote;
`line[first_quote + 1..].find('"')` (searching only in the remainder)
gives you the offset of the second one relative to that remainder --
add `first_quote + 1` back if you need an absolute offset, or just keep
working with sub-slices of the remainder the way the rest of this hint
does. The text strictly between the two quotes is the request section:
`"GET /api/products HTTP/1.1"` minus the quotes themselves.

`request.split_whitespace()` gives you an iterator; `.next()` three times
gets you method, path, and the HTTP-version token you don't care about.
The `?` operator on `Iterator::next()`'s `Option` is exactly the idiom you
want here (a function returning `Option<ParsedLine>` can use `?` on any
other `Option`-returning expression, propagating `None` automatically) --
same shape as using `?` with `Result` in module 01, just for the other
error-carrying type. If a 4th `.next()` call returns `Some(_)` instead of
`None`, that's the "extra token" corruption mode -- reject it.

The status token is the first whitespace-separated word in whatever comes
*after* the second quote. `after_second_quote.split_whitespace().next()`
gets it; `.parse::<u16>().ok()?` turns a parse failure into the `None` you
need to return (`.ok()` converts `Result<u16, _>` to `Option<u16>`,
discarding the specific parse error since `parse_log_line` only needs
`Option`, not a typed error).

## `App::handle_event`

```text
match event {
    Event::NewLine(line) => {
        self.total_lines += 1;
        match parse_log_line(&line) {
            Some(parsed) => {
                *self.status_counts.entry(status_class(parsed.status).to_string()).or_insert(0) += 1;
                *self.path_counts.entry(parsed.path).or_insert(0) += 1;   // parsed.path is already owned
                if self.recent_lines.len() >= RECENT_LINES_CAPACITY {
                    self.recent_lines.pop_front();
                }
                self.recent_lines.push_back(line);   // the RAW line, not a reconstruction from `parsed`
            }
            None => self.malformed_lines += 1,
        }
    }
    Event::Tick => self.tick_count += 1,
    Event::Resize(w, h) => { self.width = w; self.height = h; }
    Event::Quit => self.should_quit = true,
}
```

Note the ordering inside the `NewLine` arm: `total_lines` increments
*before* you even try to parse, unconditionally -- it's not inside either
branch of the `match parse_log_line(...)`.

## `render`

`Layout::vertical([Constraint::Length(3), Constraint::Length(8),
Constraint::Min(0)]).areas(frame.area())` destructures directly into a
`[Rect; 3]` via array pattern -- no need to call `.split(...)` and index
into a slice. The same `Layout::horizontal([...]).areas(...)` pattern
splits one of those areas again for the two side-by-side panes.

`Paragraph::new(some_string)` and `List::new(vec_of_list_items)` both
implement `Widget`, so `frame.render_widget(widget, area)` accepts either
directly. `Block::new().borders(Borders::ALL).title("...")` chained onto
`.block(...)` on a `Paragraph`/`List` gets you a bordered, titled pane --
entirely optional visually, but it makes the areas visible from each
other when you're debugging layout by eye via `cargo run`.

For the status-breakdown pane, iterating a `BTreeMap<String, u64>` with
`.iter()` already comes out in sorted-key order -- no extra `.sort()`
needed before turning each `(class, count)` pair into a `ListItem`. For
the top-paths pane, call `app.top_paths(n)` for some small fixed `n` (5 is
reasonable) rather than rendering the full histogram.
