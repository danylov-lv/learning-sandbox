# 06 -- TUI Log Dashboard

## Backstory

The aggregates from task 01 answer "what happened over the whole file."
They don't answer "what's happening right now" -- for that, someone needs
to be staring at a dashboard that updates as requests come in: current
throughput, which status codes are showing up, which endpoints are hot,
without re-running a batch job every few seconds. That's a TUI (terminal
UI) job, and `ratatui` is the crate the Rust ecosystem reaches for.

The trap most people fall into building one of these is letting terminal
I/O, timing, and application state tangle into one big event loop that's
impossible to test without literally driving a terminal. This task is
built to make that mistake structurally awkward: the state (`App`) and
the two things that touch it (`handle_event` and `render`) know nothing
about `crossterm`, threads, or files. Everything that actually reads a
keypress or tails a file lives in `main.rs`, which nothing in `tests/`
ever runs.

## What's given

- `src/lib.rs` -- a scaffold: `Event` (fully defined, the enum every
  state change flows through), `ParsedLine` (fully defined), `App` (fully
  defined -- a plain data struct, every field `pub`), and four `todo!()`
  functions/methods: `parse_log_line`, `status_class`,
  `App::new`/`App::handle_event`/`App::top_paths`, and `render`. The exact
  line format and the exact per-`Event`-variant contract are both
  documented in the module-level doc comment at the top of the file --
  read it before writing any code.
- `src/main.rs` -- a real but ungraded CLI: the actual `crossterm` event
  loop that tails a log file and drives this crate's `App`/`render` live
  in a terminal. Nothing in `tests/` executes this binary.
- `tests/` -- the validator, in three files: `parse_log_line.rs` (unit
  tests for the string-parsing half, independent of `App`),
  `app_event_handling.rs` (scripted `Event` sequences against
  `App::handle_event`, asserting on the resulting state), and
  `render_test_backend.rs` (renders `App` into a
  `ratatui::backend::TestBackend` and asserts on specific cell contents).
  None of these open a real terminal, and none of them read
  `data/access.log` -- every input is a literal in the test file itself.

## What's required

Implement the five `todo!()` pieces in `src/lib.rs`:

1. **`parse_log_line`** -- extract method, path, and status from one raw
   log line (same format as `data/access.log`/module 01, but you only
   need three of its fields). Returns `None`, never panics, on anything
   that doesn't match.
2. **`status_class`** -- map a status code to its `"1xx"`.."5xx"` class
   label.
3. **`App::new`** -- an all-zero/empty/false starting state.
4. **`App::handle_event`** -- the core seam. An exhaustive `match` over
   `Event`'s four variants, each touching only the fields the module doc
   comment says it should.
5. **`App::top_paths`** -- top `n` paths by count, descending, tied paths
   broken by name ascending.
6. **`render`** -- draw `app`'s state into `frame`: a header, a
   status-code breakdown, a top-paths list, and the recent-lines ring
   buffer. Never mutates `app`.

## Completion criteria

```bash
cd 18-rust-track
cargo test -p t06-tui-log-dashboard
```

All given tests pass. They cover, at minimum:

- `parse_log_line` correctly extracts method/path/status from a
  well-formed line and correctly rejects every malformed shape described
  in the module docs (no quotes, wrong token count, a path not starting
  with `/`, a non-numeric status, truncation), plus empty/whitespace-only
  input.
- A scripted sequence of `Event::NewLine` (well-formed and malformed
  interleaved), `Event::Tick`, `Event::Resize`, and `Event::Quit` produces
  exactly the state the module docs promise: malformed lines bump
  `malformed_lines` and touch nothing else; well-formed lines update
  `status_counts`/`path_counts`/`recent_lines`; `Tick`/`Resize`/`Quit`
  each touch only their own field(s) and leave everything else untouched.
- `recent_lines` behaves as a true ring buffer: capped at
  `RECENT_LINES_CAPACITY`, oldest-evicted-first, malformed lines never
  occupying a slot.
- `top_paths` orders by count descending with a path-name-ascending
  tiebreak, and truncates correctly.
- Rendering two different `App` states into a `TestBackend` produces
  visibly different screens, each containing its own total/malformed
  counts, more than one status class, and more than one path name --
  a `render` that ignores `self`, or a `App`/`top_paths` that collapses
  to one hardcoded entry, fails multiple tests at once.

## Estimated evenings

1-2

## Topics to read up on

- `ratatui`'s core mental model: an immediate-mode UI where you redraw
  the whole screen every frame from your own state, rather than mutating
  persistent widget objects
- `Layout`/`Constraint`: how a `Rect` gets split into sub-`Rect`s, and the
  difference between `Length`, `Percentage`, and `Min`/`Max` constraints
- `Frame::render_widget` and the `Widget` trait: why `Paragraph`, `List`,
  and even a plain `&str` all implement it
- `ratatui::backend::TestBackend`: rendering into an in-memory buffer
  instead of a real terminal, and what a `Buffer`'s `content`/`area`
  actually store
- `VecDeque` as a ring buffer: `push_back`/`pop_front`, and why it's the
  right structure instead of a `Vec` with manual index bookkeeping
- Exhaustive `match` over an enum as an architectural discipline, not just
  a syntax requirement -- what it buys you when every variant must touch
  a disjoint slice of state
- The "seam" concept in testable architecture: why isolating all I/O
  behind one function (`main`'s event loop, here) so that the rest of the
  program is pure functions is what makes a stateful, interactive program
  testable at all
- `crossterm`'s event/terminal-mode API (`enable_raw_mode`,
  `EnterAlternateScreen`, `event::poll`/`event::read`) -- needed for
  `main.rs`, not for anything graded

## Off-limits until you're done

`.authoring/design.md` at the module root documents this task's grading
internals -- read it after you've passed the tests, if at all, not before.
