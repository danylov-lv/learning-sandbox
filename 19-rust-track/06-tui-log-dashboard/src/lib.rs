//! t06-tui-log-dashboard.
//!
//! A live `ratatui` dashboard over a tailed `access.log`-shaped stream: a
//! header, a status-code-class breakdown, a top-paths list, and a ring
//! buffer of the most recent lines. The whole crate is built around one
//! seam: [`App`] is a plain data struct with no I/O anywhere near it, and
//! every state change flows through [`App::handle_event`] matching on
//! [`Event`]. `main.rs` is where `crossterm` actually reads the terminal and
//! tails a file — this library never touches either, which is exactly what
//! makes it deterministic to test.
//!
//! ## Line format (same shape as `data/access.log`, module 01)
//!
//! ```text
//! 108.204.108.63 - - [01/Jan/2024:00:00:02 +0000] "GET /api/products HTTP/1.1" 200 60258 "-" "Mozilla/5.0 (compatible; sandbox18-bot/1.0)" 18.4
//! ```
//!
//! [`parse_log_line`] only needs three fields out of that: the method and
//! path inside the quoted request (`"GET /api/products HTTP/1.1"`), and the
//! numeric status code that follows the closing quote. Everything else
//! (IP, timestamp, bytes, referrer, user-agent, response time) is ignored
//! by this task — the dashboard never uses them.
//!
//! A line is malformed (and must come back as `None`, never a panic and
//! never a best-guess `ParsedLine`) if: there's no quoted request section
//! at all, the quoted section doesn't have exactly `METHOD PATH
//! HTTP/x.y` (extra or missing tokens), the path doesn't start with `/`,
//! or the token right after the closing quote isn't a valid `u16`.
//!
//! ## What `App::handle_event` must guarantee
//!
//! - `Event::NewLine(line)` always increments `total_lines`, whether or not
//!   `line` parses.
//! - A malformed line additionally increments `malformed_lines` and stops
//!   there — it must not appear in `status_counts`, `path_counts`, or
//!   `recent_lines`. "Skipped, not miscounted": the *only* trace a
//!   malformed line leaves behind is the `malformed_lines` counter.
//! - A well-formed line updates `status_counts` (keyed by [`status_class`])
//!   and `path_counts` (keyed by the full path), and pushes the raw line
//!   (not the parsed pieces) onto the back of `recent_lines`, evicting the
//!   oldest entry once the ring buffer is at [`RECENT_LINES_CAPACITY`].
//! - `Event::Tick` only ever increments `tick_count` — it never touches any
//!   of the log-derived fields above.
//! - `Event::Resize(w, h)` only ever overwrites `width`/`height`.
//! - `Event::Quit` only ever sets `should_quit`.
//!
//! Note what that list implies: every variant of `Event` touches a
//! disjoint slice of `App`'s fields. An implementation that, say, bumps
//! `tick_count` on every event, or drops `recent_lines` on `Resize`, fails
//! the exhaustive-match discipline the tests check for.

use std::collections::{BTreeMap, HashMap, VecDeque};

use ratatui::Frame;

/// How many of the most recently ingested well-formed lines [`App`] keeps
/// around for the "recent lines" pane. A `Event::NewLine` past this
/// capacity evicts the oldest entry — this is a ring buffer, not an
/// ever-growing `Vec`.
pub const RECENT_LINES_CAPACITY: usize = 8;

/// The one and only way [`App`]'s state changes. Nothing in this crate
/// mutates `App` except by matching on this enum — that's what makes
/// [`App::handle_event`] a seam a test can drive without a terminal, a
/// thread, or a file on disk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Event {
    /// A periodic timer tick (real `main.rs` fires this roughly once a
    /// second). Advances `tick_count` only.
    Tick,
    /// One raw line read from the tailed log file, not yet parsed.
    NewLine(String),
    /// The terminal was resized to `(width, height)` in cells.
    Resize(u16, u16),
    /// The user asked to quit (real `main.rs` maps a keypress to this).
    Quit,
}

/// The three fields this dashboard needs out of one access-log line. See
/// the module docs above for the exact format and what counts as
/// malformed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedLine {
    pub method: String,
    pub path: String,
    pub status: u16,
}

/// Parses one raw log line into a [`ParsedLine`], or `None` if it doesn't
/// match the format described in the module docs. Never panics.
pub fn parse_log_line(line: &str) -> Option<ParsedLine> {
    todo!(
        "find the '\"'-quoted request section, split it into exactly three \
         whitespace-separated tokens (method, path, http-version), require the path to \
         start with '/', then parse the token right after the closing quote as the u16 \
         status code"
    )
}

/// Which status-code class (`"1xx"`..`"5xx"`) a status code belongs to.
/// A status outside `100..=599` (not something the real data ever
/// produces, but `parse_log_line` doesn't rule it out structurally) maps to
/// `"other"`.
pub fn status_class(status: u16) -> &'static str {
    todo!("integer-divide by 100 and match 1..=5 to \"1xx\"..\"5xx\", anything else to \"other\"")
}

/// The dashboard's entire state. Plain data, no I/O — every field here is
/// updated exclusively through [`App::handle_event`], never mutated
/// directly from outside this module in real usage.
#[derive(Debug, Clone, PartialEq)]
pub struct App {
    /// Every `NewLine` event seen, well-formed or not.
    pub total_lines: u64,
    /// The subset of `total_lines` that failed to parse.
    pub malformed_lines: u64,
    /// Keyed by [`status_class`]; only classes actually observed have an
    /// entry (no pre-seeded zeros). `BTreeMap` so iteration order used by
    /// `render` is deterministic (`"2xx"` before `"4xx"` before `"5xx"`,
    /// etc.) without a separate sort step.
    pub status_counts: BTreeMap<String, u64>,
    /// Full per-path request histogram, well-formed lines only.
    pub path_counts: HashMap<String, u64>,
    /// The most recent well-formed raw lines, oldest first, capped at
    /// [`RECENT_LINES_CAPACITY`].
    pub recent_lines: VecDeque<String>,
    /// Number of `Event::Tick`s handled so far.
    pub tick_count: u64,
    /// Last known terminal width in cells, from the most recent
    /// `Event::Resize` (0 until the first one arrives).
    pub width: u16,
    /// Last known terminal height in cells, from the most recent
    /// `Event::Resize` (0 until the first one arrives).
    pub height: u16,
    /// Set once by `Event::Quit`; real `main.rs`'s event loop checks this
    /// after every `handle_event` call and exits when it's `true`.
    pub should_quit: bool,
}

impl App {
    /// A fresh dashboard: every counter zero, every collection empty,
    /// `should_quit` false.
    pub fn new() -> Self {
        todo!("build Self with all-zero/empty/false fields")
    }

    /// Applies one [`Event`], mutating `self` per the contract spelled out
    /// in the module docs above. The `match` must be exhaustive over all
    /// four variants — each one touches a disjoint slice of `self`'s
    /// fields.
    pub fn handle_event(&mut self, event: Event) {
        todo!(
            "match on `event`; for NewLine, always bump total_lines, then try \
             parse_log_line — on None bump malformed_lines and stop, on Some update \
             status_counts/path_counts and push_back the raw line onto recent_lines \
             (pop_front first if already at RECENT_LINES_CAPACITY); for Tick bump \
             tick_count; for Resize overwrite width/height; for Quit set should_quit"
        )
    }

    /// Top `n` paths by request count, descending; ties broken by path
    /// name ascending, so the ordering is deterministic regardless of
    /// `HashMap` iteration order.
    pub fn top_paths(&self, n: usize) -> Vec<(String, u64)> {
        todo!(
            "collect self.path_counts into a Vec<(String, u64)>, sort by count desc then \
             path asc, truncate to n"
        )
    }
}

impl Default for App {
    fn default() -> Self {
        Self::new()
    }
}

/// Draws the whole dashboard into `frame`: a one-line header, a
/// status-code breakdown and a top-paths list side by side below it, and
/// the recent-lines ring buffer filling the rest. Reads `app`, never
/// mutates it.
///
/// This is the function the real `main.rs` passes to `Terminal::draw`
/// every frame, and the function the given tests call directly against a
/// `ratatui::backend::TestBackend`-backed `Terminal` — it must not assume
/// anything about the backend beyond what `Frame` exposes.
pub fn render(app: &App, frame: &mut Frame) {
    todo!(
        "Layout::vertical([Constraint::Length(3), Constraint::Length(8), Constraint::Min(0)]) \
         over frame.area() for [header, stats_row, recent_lines]; render a header Paragraph \
         (include app.total_lines and app.malformed_lines somewhere in its text so the \
         rendered header actually changes with app state); split stats_row horizontally in \
         two for a status_counts breakdown (Paragraph or List, one line per class, e.g. \
         \"2xx: 12\") and a top_paths List (via app.top_paths(5), one ListItem per \
         \"path (count)\"); render recent_lines as a List of its contents, oldest first"
    )
}
