# 18-rust-track — live-verification notes

Off-limits to the learner (spoiler record), same rule as `design.md`. This
is the final generation session's verification gate: the module's content
was authored in prior sessions but had never been committed and had no
verification record. This session built the workspace, proved every task's
pass-path live, and confirmed every stock stub fails cleanly.

## Environment

- Windows, `rustc`/`cargo` 1.95.0. Edition 2024, resolver 3, workspace at
  `18-rust-track/Cargo.toml`; `Cargo.lock` committed.
- Full workspace builds clean (`cargo build --workspace`) — only expected
  stub warnings (unused params on `todo!()`-bodied functions).

## Data determinism

`cargo run -p sandbox18-datagen` at `SCALE=1.0` reproduced the committed
`data/ground-truth.json` **byte-identical**
(sha256 `478fe29b21686aab7340938af2e3ba3bab65b0d2338b3dce5fc5938cadb681da`),
and `access.log` (27,482,506 bytes) / `products.csv` (30,421,286 bytes) to
the same sizes. Fixed seed `0xC0FFEE_5EED`. Only `ground-truth.json` is
committed; the two large data files are gitignored.

## Pass-path verification (one throwaway reference impl per task)

Each task was verified by a subagent that: backed up the stub, wrote a
correct reference implementation in place (public signatures unchanged),
ran `cargo test -p <package>`, confirmed all tests pass, then restored the
stub byte-identical (sha256 re-checked by the orchestrator against the
committed tree) and re-ran to confirm a clean fail. No reference solution
was ever committed. Results:

| Task | Package | Tests passed (ref impl) | Restored stub sha256 |
|---|---|---|---|
| 01 | t01-log-parser-aggregations | 29 (parse 9 / hand-built 12 / ground-truth 8) | `cbfa4d68…fef95ec` |
| 02 | t02-toy-expression-interpreter | 62 (incl. 900-tree property suite) | `aecf09ae…abd0487` |
| 03 | t03-csv-to-parquet | 20 (parse 11 / fixture 3 / ground-truth 6) | `1d0885cc…d5b0c37` |
| 04 | t04-url-health-checker | 11 (cap 2 / fake seam 4 / http 5) | `d8a16a2b…4e8b64f1` |
| 05 | t05-bitcask-kv-store | 13 (basic 8 / reopen 2 / compaction 1 / crash 1 / model 1) | `02b8b2cf…b278dc53` |
| 06 | t06-tui-log-dashboard | 30 (parse 13 / events 12 / TestBackend 5) | `abf67336…ff5b68db` |
| 07 | t07-async-fetch-pipeline | 13 (cap 2 / fake seam 5 / tcp 6) | `106fa724…dca2699a5` |
| 08 | t08-capstone-price-watch | 7 (cp1 2 / cp2 1 / cp3 4) | `2c5ab1f1…232b0c06` |
| bonus | t09-proc-macro-bonus | 12 (4 / 4 / 4) | `f98fc67d…84b90e4d9` |

Capstone `DESIGN.md` was filled to pass cp3's `design_memo_is_filled_in`
gate during verification, then restored to the unfilled template
(sha256 `f2c2b667…09057257`; every section still carries the `[fill in`
marker).

## Stock fail-mode (verified before implementing)

All eight non-macro tasks fail cleanly on the stock stub: the graded tests
panic with `not yet implemented: …` (the `todo!()` message), `cargo test`
exits non-zero, and the panic message is the diagnosis. The capstone cp3
`design_memo_is_filled_in` test additionally rejects the unfilled template.

**proc-macro exception:** t09's stub is a `#[derive(Builder)]` whose body is
`todo!()`, so on the stock stub the dependent tests fail *at compile time*
(`error: proc-macro derive panicked` + the `todo!` help message, cascading
into `E0599 no method builder`), `cargo` exits 101. This compile-time panic
is the only possible clean-fail for a stubbed derive and is documented in
the task README's "how the stub fails" section — accepted as clean.

## No-leak / anti-cheat confirmation

- Every committed `src/lib.rs` (9 files) retains `todo!()`/`unimplemented!()`
  and contains only public signatures + guidance doc-comments — no solution
  logic. All `NOTES.md` are unfilled templates; the capstone `DESIGN.md` is
  the unfilled template.
- No `.bak`, scratch, `target/`, `access.log`, or `products.csv` tracked
  (git dry-run: 122 clean files under the module). Backups lived only in the
  OS temp dir.
- Tests grade against `ground-truth.json` (01/03/06/08) or hand-authored /
  independently-recomputed expectations (02/04/05/07/09), never the
  learner's own re-derivation. Concurrency caps are asserted structurally
  from the fixture servers' own atomic counters (`stats().max_concurrency`,
  e.g. cp3 observed `== 3` for CAP 3), retry by request count against
  `fail_first(n)` — never a wall-clock gate.

## Platform / API notes for future sessions

- **Windows connect errors (task 04):** `TcpStream::connect_timeout` to a
  refused port surfaces as `ErrorKind::TimedOut`, not `ConnectionRefused`,
  so a correct checker must treat all connect-level errors as retryable
  connection failures (the only tested connect contract is refused →
  `ConnectionFailed`). Not a test bug.
- **arrow/parquet 59.1.0 (task 03):** `WriterProperties::set_max_row_group_row_count`
  is the row-group-size API the README specifies; it exists and compiles.
- **ratatui 0.30.2 (task 06):** `frame.area()`, `Layout::vertical/horizontal`,
  `TestBackend` buffer assertions — current 0.30 API, compiles clean.
- **bitcask recovery (tasks 05/08):** replay must distinguish clean EOF from
  a torn header / torn record / checksum mismatch and `set_len`-truncate the
  torn tail; `compact()` on Windows must drop the append handle before
  `rename` to avoid a sharing violation. Crash-injection offsets in the
  tests are reachable (cp1 cuts inside the torn record's value half; cp3
  removes the final byte).

## Note on hints

`02-toy-expression-interpreter/hints/hint-3.md` carries near-complete
*pseudocode* for all three stages (tokenizer/parser/evaluator). It is
explicitly labelled non-copy-pasteable ("You still have to translate this
into working Rust — types, borrow-checking, exact error variants") and is
the last-resort tier, consistent with this repo's hint-3 definition
("concrete approach, still no ready code"). Kept as-is.
