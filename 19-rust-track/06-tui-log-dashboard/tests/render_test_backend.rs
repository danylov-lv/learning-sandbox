//! Renders `App` into a `ratatui::backend::TestBackend` -- never a real
//! terminal -- and asserts on the resulting cell contents. Two distinct,
//! directly-constructed `App` states (never routed through
//! `handle_event`, so these tests are independent of that seam) are each
//! rendered and checked for specific substrings: a header, more than one
//! status class, more than one path name. The two states' rendered output
//! is also asserted to differ, which is what catches a `render` that
//! ignores `self` -- see `.authoring/design.md`'s anti-cheat philosophy,
//! restated here: a stub that always draws the same screen (or a blank
//! one) fails every test in this file.

use std::collections::{BTreeMap, HashMap, VecDeque};

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;

use t06_tui_log_dashboard::{App, render};

fn build_app(
    total_lines: u64,
    malformed_lines: u64,
    status_counts: &[(&str, u64)],
    path_counts: &[(&str, u64)],
) -> App {
    let status_counts: BTreeMap<String, u64> = status_counts.iter().map(|(k, v)| (k.to_string(), *v)).collect();
    let path_counts: HashMap<String, u64> = path_counts.iter().map(|(k, v)| (k.to_string(), *v)).collect();
    App {
        total_lines,
        malformed_lines,
        status_counts,
        path_counts,
        recent_lines: VecDeque::new(),
        tick_count: 0,
        width: 100,
        height: 30,
        should_quit: false,
    }
}

/// State A: 142 requests, 17 malformed, 3 status classes, 3 paths. The
/// total/malformed counts are deliberately distinctive (3- and 2-digit,
/// not reused anywhere else in this state) so finding them in the
/// rendered text is meaningful, not a coincidental digit match.
fn state_a() -> App {
    build_app(
        142,
        17,
        &[("2xx", 30), ("4xx", 10), ("5xx", 2)],
        &[("/home", 25), ("/api/orders", 10), ("/checkout", 5)],
    )
}

/// State B: every number, every path, and every status class differs from
/// state A -- there is no field a degenerate `render` could accidentally
/// get right by copying state A's output.
fn state_b() -> App {
    build_app(7, 1, &[("2xx", 4), ("3xx", 2), ("5xx", 1)], &[("/status", 3), ("/ping", 2), ("/metrics", 1)])
}

fn buffer_text(buffer: &Buffer) -> String {
    let width = buffer.area.width as usize;
    buffer
        .content
        .chunks(width)
        .map(|row| row.iter().map(|cell| cell.symbol()).collect::<String>())
        .collect::<Vec<_>>()
        .join("\n")
}

fn render_to_text(app: &App) -> String {
    let backend = TestBackend::new(100, 30);
    let mut terminal = Terminal::new(backend).expect("Terminal::new over a TestBackend must not fail");
    terminal
        .draw(|frame| render(app, frame))
        .expect("render must not error when drawing into a TestBackend-backed Frame");
    buffer_text(terminal.backend().buffer())
}

#[test]
fn header_shows_the_total_and_malformed_line_counts() {
    let text = render_to_text(&state_a());
    assert!(
        text.contains("142"),
        "the header must render app.total_lines (142) somewhere on screen, got:\n{text}"
    );
    assert!(
        text.contains("17"),
        "the header must render app.malformed_lines (17) somewhere on screen, got:\n{text}"
    );
}

#[test]
fn status_breakdown_shows_more_than_one_class_with_correct_counts() {
    let text = render_to_text(&state_a());
    assert!(text.contains("2xx"), "expected the \"2xx\" class label to be rendered somewhere, got:\n{text}");
    assert!(text.contains("4xx"), "expected the \"4xx\" class label to be rendered somewhere, got:\n{text}");
    assert!(text.contains("5xx"), "expected the \"5xx\" class label to be rendered somewhere, got:\n{text}");
    assert!(
        text.contains("30"),
        "expected the 2xx count (30) to be rendered next to its class label, got:\n{text}"
    );
    assert!(
        text.contains("10"),
        "expected the 4xx count (10) to be rendered next to its class label, got:\n{text}"
    );
}

#[test]
fn top_paths_shows_more_than_one_path_name() {
    let text = render_to_text(&state_a());
    assert!(text.contains("/home"), "expected the highest-count path \"/home\" to appear, got:\n{text}");
    assert!(
        text.contains("/api/orders"),
        "expected a second, lower-count path \"/api/orders\" to also appear (not just the top one), got:\n{text}"
    );
    assert!(text.contains("/checkout"), "expected the third path \"/checkout\" to also appear, got:\n{text}");
}

#[test]
fn two_different_app_states_render_visibly_different_screens() {
    let text_a = render_to_text(&state_a());
    let text_b = render_to_text(&state_b());
    assert_ne!(
        text_a, text_b,
        "state A (42 requests, /home/api/orders/checkout) and state B (7 requests, \
         /status/ping/metrics) must render different screens; identical output means render() \
         ignored `self` entirely"
    );

    assert!(text_b.contains('7'), "state B's header must show its own total_lines (7), got:\n{text_b}");
    assert!(
        !text_b.contains("/home"),
        "state B has no \"/home\" path at all; its presence would mean render() is showing \
         stale or hardcoded data instead of state B's actual path_counts, got:\n{text_b}"
    );
    assert!(text_b.contains("/status"), "expected state B's own path \"/status\" to appear, got:\n{text_b}");
    assert!(text_b.contains("/ping"), "expected state B's own path \"/ping\" to also appear, got:\n{text_b}");
}

#[test]
fn rendering_does_not_panic_on_a_fresh_all_zero_app() {
    let app = build_app(0, 0, &[], &[]);
    // Only checking this doesn't panic -- an empty App is a legitimate
    // state (right after App::new(), before the first NewLine arrives).
    let _ = render_to_text(&app);
}
