//! Drives `App::handle_event` with scripted sequences of `Event`s and
//! asserts on the resulting state -- exactly what the module docs promise:
//! `NewLine` on a malformed line only ever bumps `malformed_lines`, `Tick`
//! only ever bumps `tick_count`, `Resize` only ever overwrites
//! `width`/`height`, `Quit` only ever sets `should_quit`. No terminal, no
//! file, no thread anywhere in this file -- `App` is plain data.

use std::collections::BTreeMap;

use t06_tui_log_dashboard::{App, Event, RECENT_LINES_CAPACITY};

/// Builds one well-formed access-log line with the given method/path/status,
/// in the format documented on `parse_log_line`.
fn line(method: &str, path: &str, status: u16) -> String {
    format!(
        "10.0.0.1 - - [01/Jan/2024:00:00:00 +0000] \"{method} {path} HTTP/1.1\" {status} 100 \"-\" \"UA\" 12.3"
    )
}

/// 12 well-formed lines across 5 distinct paths (counts: "/" x4,
/// "/api/products" x3, "/login" x2, "/api/cart" x2, "/health" x1) with 3
/// malformed lines interspersed at arbitrary points. Counts and status
/// classes below are all hand-computed from this exact list, never
/// re-derived from `App` itself.
fn scripted_lines() -> Vec<Event> {
    vec![
        Event::NewLine(line("GET", "/", 200)),
        Event::NewLine(line("GET", "/api/products", 200)),
        Event::NewLine("this is not a log line at all".to_string()),
        Event::NewLine(line("GET", "/", 200)),
        Event::NewLine(line("POST", "/api/products", 500)),
        Event::NewLine(String::new()),
        Event::NewLine(line("GET", "/login", 200)),
        Event::NewLine(line("GET", "/", 404)),
        Event::NewLine(line("GET", "/api/cart", 200)),
        Event::NewLine(line("GET", "/api/products", 200)),
        Event::NewLine("1.2.3.4 - - [01/Jan/2024:00:00:00 +0000] \"GET /x HTTP/1.1\" UNKNOWN 1 \"-\" \"UA\" 1.0".to_string()),
        Event::NewLine(line("GET", "/", 200)),
        Event::NewLine(line("GET", "/login", 403)),
        Event::NewLine(line("GET", "/api/cart", 200)),
        Event::NewLine(line("GET", "/health", 200)),
    ]
}

fn app_after_scripted_lines() -> App {
    let mut app = App::new();
    for event in scripted_lines() {
        app.handle_event(event);
    }
    app
}

#[test]
fn total_well_formed_and_malformed_line_counts_are_exact() {
    let app = app_after_scripted_lines();
    assert_eq!(app.total_lines, 15, "the scripted corpus has exactly 15 NewLine events");
    assert_eq!(app.malformed_lines, 3, "3 of the 15 lines are malformed (no quotes, empty, non-numeric status)");
    assert_eq!(
        app.total_lines - app.malformed_lines,
        12,
        "well-formed count must be total minus malformed -- every line is one or the other, never both, never neither"
    );
}

#[test]
fn malformed_lines_are_skipped_not_miscounted() {
    // Only malformed lines: total_lines must still track them, but nothing
    // else may move.
    let mut app = App::new();
    app.handle_event(Event::NewLine("garbage one".to_string()));
    app.handle_event(Event::NewLine(String::new()));
    app.handle_event(Event::NewLine("also garbage".to_string()));

    assert_eq!(app.total_lines, 3, "every NewLine event counts toward total_lines, malformed or not");
    assert_eq!(app.malformed_lines, 3, "all 3 lines here are malformed");
    assert!(
        app.status_counts.is_empty(),
        "no well-formed line was ever seen, so status_counts must have no entries at all, not zero-valued ones"
    );
    assert!(app.path_counts.is_empty(), "no well-formed line was ever seen, so path_counts must be empty");
    assert!(
        app.recent_lines.is_empty(),
        "malformed lines must never appear in the recent-lines ring buffer"
    );
}

#[test]
fn status_counts_match_hand_computed_expectation_and_cover_more_than_one_class() {
    let app = app_after_scripted_lines();
    let expected: BTreeMap<String, u64> =
        [("2xx".to_string(), 9), ("4xx".to_string(), 2), ("5xx".to_string(), 1)].into_iter().collect();
    assert_eq!(
        app.status_counts, expected,
        "9 lines are 2xx (all the 200s), 2 are 4xx (one 404 + one 403), 1 is 5xx (the 500); a \
         degenerate implementation that returns only one class or a constant map fails here"
    );
}

#[test]
fn path_counts_match_hand_computed_expectation_and_cover_more_than_one_path() {
    let app = app_after_scripted_lines();
    let expected: BTreeMap<&str, u64> =
        [("/", 4), ("/api/products", 3), ("/login", 2), ("/api/cart", 2), ("/health", 1)].into_iter().collect();
    for (path, count) in &expected {
        assert_eq!(
            app.path_counts.get(*path).copied().unwrap_or(0),
            *count,
            "expected {count} requests to {path}, found {:?}",
            app.path_counts.get(*path)
        );
    }
    assert_eq!(
        app.path_counts.len(),
        expected.len(),
        "path_counts must have exactly {} distinct paths, found {}: {:?}",
        expected.len(),
        app.path_counts.len(),
        app.path_counts
    );
}

#[test]
fn top_paths_orders_by_count_descending_with_path_ascending_tiebreak() {
    let app = app_after_scripted_lines();
    let top = app.top_paths(10);
    let expected = vec![
        ("/".to_string(), 4),
        ("/api/products".to_string(), 3),
        ("/api/cart".to_string(), 2),
        ("/login".to_string(), 2),
        ("/health".to_string(), 1),
    ];
    assert_eq!(
        top, expected,
        "\"/api/cart\" and \"/login\" tie at count 2 and must be ordered by path name ascending \
         (\"/api/cart\" < \"/login\"); the rest is a strict count-descending order"
    );
}

#[test]
fn top_paths_truncates_to_n() {
    let app = app_after_scripted_lines();
    let top = app.top_paths(2);
    assert_eq!(
        top,
        vec![("/".to_string(), 4), ("/api/products".to_string(), 3)],
        "top_paths(_, 2) must return only the 2 highest-count paths, not the full histogram"
    );
}

#[test]
fn top_paths_on_a_directly_built_tie_breaks_by_path_name() {
    // Bypasses handle_event entirely -- App's fields are public, so this
    // pins down top_paths' sort/tiebreak logic on its own, independent of
    // the parsing/ingestion path above.
    let mut app = App::new();
    app.path_counts.insert("/zzz".to_string(), 1);
    app.path_counts.insert("/api".to_string(), 2);
    app.path_counts.insert("/".to_string(), 2);

    let top = app.top_paths(10);
    assert_eq!(
        top,
        vec![("/".to_string(), 2), ("/api".to_string(), 2), ("/zzz".to_string(), 1)],
        "\"/\" and \"/api\" tie on count 2 and must sort by path name ascending; \"/zzz\" trails at count 1"
    );
}

#[test]
fn recent_lines_ring_buffer_keeps_only_the_last_capacity_well_formed_lines_in_order() {
    let mut app = App::new();
    // 10 well-formed lines, each with a uniquely identifiable path, plus 2
    // malformed lines interspersed -- the malformed ones must not consume a
    // ring-buffer slot or shift the ordering of the well-formed ones.
    for i in 0..10 {
        app.handle_event(Event::NewLine(line("GET", &format!("/line-{i}"), 200)));
        if i == 3 || i == 7 {
            app.handle_event(Event::NewLine("garbage".to_string()));
        }
    }

    assert_eq!(
        app.recent_lines.len(),
        RECENT_LINES_CAPACITY,
        "with 10 well-formed lines pushed and a capacity of {RECENT_LINES_CAPACITY}, the ring \
         buffer must be exactly full, not still growing and not overflowing"
    );

    let expected_paths: Vec<String> = (10 - RECENT_LINES_CAPACITY..10).map(|i| format!("/line-{i}")).collect();
    for (recent, expected_path) in app.recent_lines.iter().zip(expected_paths.iter()) {
        assert!(
            recent.contains(expected_path),
            "expected the ring buffer, oldest-first, to contain the last {RECENT_LINES_CAPACITY} \
             well-formed lines in arrival order; expected a line mentioning {expected_path}, got {recent:?}"
        );
    }
    assert!(
        !app.recent_lines.iter().any(|l| l.contains("garbage")),
        "the two malformed \"garbage\" lines must never appear in recent_lines"
    );
}

#[test]
fn tick_only_advances_tick_count_and_touches_nothing_else() {
    let mut app = App::new();
    app.handle_event(Event::NewLine(line("GET", "/", 200)));
    let before = app.clone();

    app.handle_event(Event::Tick);
    app.handle_event(Event::Tick);
    app.handle_event(Event::Tick);

    assert_eq!(app.tick_count, 3, "3 Tick events must advance tick_count by exactly 3");
    assert_eq!(app.total_lines, before.total_lines, "Tick must not touch total_lines");
    assert_eq!(app.malformed_lines, before.malformed_lines, "Tick must not touch malformed_lines");
    assert_eq!(app.status_counts, before.status_counts, "Tick must not touch status_counts");
    assert_eq!(app.path_counts, before.path_counts, "Tick must not touch path_counts");
    assert_eq!(app.recent_lines, before.recent_lines, "Tick must not touch recent_lines");
    assert_eq!(app.width, before.width, "Tick must not touch width");
    assert_eq!(app.height, before.height, "Tick must not touch height");
    assert!(!app.should_quit, "Tick must never set should_quit");
}

#[test]
fn resize_only_overwrites_width_and_height() {
    let mut app = App::new();
    app.handle_event(Event::NewLine(line("GET", "/", 200)));
    app.handle_event(Event::Tick);
    let before = app.clone();

    app.handle_event(Event::Resize(120, 40));

    assert_eq!(app.width, 120, "Resize(120, 40) must set width to 120");
    assert_eq!(app.height, 40, "Resize(120, 40) must set height to 40");
    assert_eq!(app.total_lines, before.total_lines, "Resize must not touch total_lines");
    assert_eq!(app.tick_count, before.tick_count, "Resize must not touch tick_count");
    assert_eq!(app.status_counts, before.status_counts, "Resize must not touch status_counts");
    assert_eq!(app.path_counts, before.path_counts, "Resize must not touch path_counts");
    assert!(!app.should_quit, "Resize must never set should_quit");

    app.handle_event(Event::Resize(10, 5));
    assert_eq!(app.width, 10, "a later Resize must overwrite width again, not accumulate");
    assert_eq!(app.height, 5, "a later Resize must overwrite height again, not accumulate");
}

#[test]
fn quit_sets_the_flag_and_touches_nothing_else() {
    let mut app = App::new();
    app.handle_event(Event::NewLine(line("GET", "/", 200)));
    app.handle_event(Event::Tick);
    app.handle_event(Event::Resize(80, 24));
    let before = app.clone();

    assert!(!before.should_quit, "should_quit must be false before any Quit event");

    app.handle_event(Event::Quit);

    assert!(app.should_quit, "Quit must set should_quit to true");
    assert_eq!(app.total_lines, before.total_lines, "Quit must not touch total_lines");
    assert_eq!(app.tick_count, before.tick_count, "Quit must not touch tick_count");
    assert_eq!(app.width, before.width, "Quit must not touch width");
    assert_eq!(app.height, before.height, "Quit must not touch height");
    assert_eq!(app.status_counts, before.status_counts, "Quit must not touch status_counts");
    assert_eq!(app.path_counts, before.path_counts, "Quit must not touch path_counts");
}

#[test]
fn a_fresh_app_starts_at_all_zero_empty_and_not_quit() {
    let app = App::new();
    assert_eq!(app.total_lines, 0);
    assert_eq!(app.malformed_lines, 0);
    assert_eq!(app.tick_count, 0);
    assert_eq!(app.width, 0);
    assert_eq!(app.height, 0);
    assert!(!app.should_quit, "a fresh App must not already be in the quit state");
    assert!(app.status_counts.is_empty(), "a fresh App has seen no lines, so no status class has an entry");
    assert!(app.path_counts.is_empty(), "a fresh App has seen no lines, so no path has an entry");
    assert!(app.recent_lines.is_empty(), "a fresh App's ring buffer starts empty");
}
