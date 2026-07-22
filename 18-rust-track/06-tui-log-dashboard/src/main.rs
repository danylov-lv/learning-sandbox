//! The real, ungraded TUI: tails `data/access.log` (or a path passed as
//! the first CLI argument) and renders `t06_tui_log_dashboard::render`
//! live via `crossterm`. `tests/` never runs this binary — it drives
//! `App::handle_event` and `render` directly against an in-memory
//! `TestBackend` instead, so nothing here affects `cargo test`.
//!
//! Usage: `cargo run -p t06-tui-log-dashboard -- [path/to/access.log]`
//! Press `q` to quit.

fn main() {
    todo!(
        "1) enable_raw_mode(), execute!(stdout, EnterAlternateScreen), build a \
         Terminal<CrosstermBackend<Stdout>>; \
         2) open the log path (std::env::args().nth(1), defaulting to something like \
         \"../data/access.log\" relative to this crate) with a BufReader positioned at \
         end-of-file (or start, your choice) and build an App::new(); \
         3) loop: crossterm::event::poll(Duration::from_millis(200)) then read() to turn a \
         KeyCode::Char('q') into Event::Quit and a resize into Event::Resize(w, h); \
         alongside that, read any newly-appended lines from the log file (or read_line in a \
         loop until it returns 0 bytes) and feed each as Event::NewLine; on a poll timeout \
         with nothing new, feed Event::Tick; \
         4) after every app.handle_event(...), terminal.draw(|f| t06_tui_log_dashboard::render(&app, f))?; \
         5) break the loop once app.should_quit, then disable_raw_mode() and \
         execute!(stdout, LeaveAlternateScreen) to restore the terminal even on an early exit"
    )
}
