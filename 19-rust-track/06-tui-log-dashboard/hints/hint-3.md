# Hint 3

Concrete approach, close to pseudocode. You still have to turn every step
below into working, compiling Rust yourself.

## `parse_log_line`

```text
first_quote = line.find('"')?
after_first = &line[first_quote + 1..]
second_quote = after_first.find('"')?
request = &after_first[..second_quote]          // "GET /api/products HTTP/1.1"

tokens = request.split_whitespace()
method = tokens.next()?.to_string()
path = tokens.next()?.to_string()
_http_version = tokens.next()?
if tokens.next().is_some() { return None }       // extra 4th token = malformed

if !path.starts_with('/') { return None }

after_request = &after_first[second_quote + 1..]
status_token = after_request.split_whitespace().next()?
status: u16 = status_token.parse().ok()?

Some(ParsedLine { method, path, status })
```

## `status_class`

```text
match status / 100 {
    1 => "1xx", 2 => "2xx", 3 => "3xx", 4 => "4xx", 5 => "5xx",
    _ => "other",
}
```

## `App::new`

Every field at its zero/empty/false value -- `BTreeMap::new()`,
`HashMap::new()`, `VecDeque::new()`, `0`, `0u16`, `0u16`, `false`. No
logic.

## `App::handle_event`

See hint-2's near-complete version of this `match` -- the one addition
worth spelling out is `top_paths`:

```text
fn top_paths(&self, n: usize) -> Vec<(String, u64)> {
    let mut paths: Vec<(String, u64)> =
        self.path_counts.iter().map(|(k, v)| (k.clone(), *v)).collect();
    paths.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    paths.truncate(n);
    paths
}
```

`b.1.cmp(&a.1)` (reversed operand order) sorts by count descending;
`.then_with(|| a.0.cmp(&b.0))` breaks ties by path name ascending only
when the counts compare equal -- this is the same two-key sort pattern as
module 01's `top_paths`.

## `render`

```text
let [header_area, stats_area, recent_area] = Layout::vertical([
    Constraint::Length(3), Constraint::Length(8), Constraint::Min(0),
]).areas(frame.area());
let [status_area, paths_area] = Layout::horizontal([
    Constraint::Percentage(50), Constraint::Percentage(50),
]).areas(stats_area);

let header = Paragraph::new(format!(
    "Log Dashboard — {} requests, {} malformed", app.total_lines, app.malformed_lines
)).block(Block::new().borders(Borders::ALL));
frame.render_widget(header, header_area);

let status_items: Vec<ListItem> = app.status_counts.iter()
    .map(|(class, count)| ListItem::new(format!("{class}: {count}")))
    .collect();
frame.render_widget(
    List::new(status_items).block(Block::new().borders(Borders::ALL).title("Status classes")),
    status_area,
);

let path_items: Vec<ListItem> = app.top_paths(5).into_iter()
    .map(|(path, count)| ListItem::new(format!("{path} ({count})")))
    .collect();
frame.render_widget(
    List::new(path_items).block(Block::new().borders(Borders::ALL).title("Top paths")),
    paths_area,
);

let recent_items: Vec<ListItem> = app.recent_lines.iter()
    .map(|line| ListItem::new(line.as_str()))
    .collect();
frame.render_widget(
    List::new(recent_items).block(Block::new().borders(Borders::ALL).title("Recent lines")),
    recent_area,
);
```

The exact wording of the header string and the exact widget choice for
each pane (`Paragraph` vs `List`) are yours to pick -- the given tests in
`tests/render_test_backend.rs` only check that specific numbers and path
strings show up somewhere on screen, never an exact layout or exact
phrasing. What they do check is that two different `App`s produce visibly
different screens, and that more than one status class / more than one
path actually get drawn -- so whatever you pick, make sure every entry in
`status_counts`/`top_paths(n)` actually reaches a widget, not just the
first one.
