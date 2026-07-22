//! Thin CLI wrapper. Not graded -- `tests/` is the validator. Useful once
//! the library is implemented, to point it at anything of your own choosing
//! (there is no real network access anywhere else in this module's tests).
//!
//! Usage: `cargo run -p t04-url-health-checker -- <url> [url...]`

fn main() {
    todo!(
        "collect std::env::args() (skip argv[0]) as the URL list, build an HttpChecker with \
         reasonable timeouts and a retry budget, call check_urls_concurrently with some fixed \
         worker count, and print each HealthReport"
    )
}
