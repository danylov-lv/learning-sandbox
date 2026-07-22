//! Thin CLI over the `t01_log_parser_aggregations` library: parses an
//! access log and prints the resulting aggregates.
//!
//! Usage: `cargo run -p t01-log-parser-aggregations -- [path/to/access.log]`
//! With no argument, defaults to this module's `data/access.log` (via
//! `sandbox18_harness::ground_truth::data_path`).

fn main() {
    todo!(
        "read an optional path from std::env::args(), defaulting to \
         sandbox18_harness::ground_truth::data_path(\"access.log\"); open it \
         with a BufReader, call t01_log_parser_aggregations::aggregate, and \
         print the resulting LogStats (e.g. with the debug formatter or a \
         hand-written summary)"
    )
}
