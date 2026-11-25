//! Full-corpus check: parse the real `data/access.log` and compare against
//! `data/ground-truth.json`, loaded through the harness's typed loader --
//! never against a second computation of the learner's own code. Run
//! `cargo run -p sandbox18-datagen` first if this fails to find the data
//! file (see the panic message from `sandbox18_harness::ground_truth::load`).
//!
//! Status/method/path/IP counts are derived only from fields that are
//! printed and parsed verbatim (no lossy formatting), so those are checked
//! for exact equality. Response-time stats are checked with a small
//! absolute tolerance: `access.log` prints response times rounded to 1
//! decimal place, while the ground truth was accumulated from the
//! full-precision values before that rounding was applied at write time --
//! an unavoidable, tiny discrepancy, not a bug in either side.

use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;

use sandbox18_harness::ground_truth;
use t01_log_parser_aggregations::{aggregate, top_paths};

fn load_stats() -> t01_log_parser_aggregations::LogStats {
    let path = ground_truth::data_path("access.log");
    let file = File::open(&path).unwrap_or_else(|e| {
        panic!(
            "failed to open {}: {e}\nhint: run `cargo run -p sandbox18-datagen` from the module root first",
            path.display()
        )
    });
    aggregate(BufReader::new(file))
}

#[test]
fn line_counts_match_ground_truth_exactly() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    assert_eq!(stats.total_lines, truth.total_lines, "total line count must match the answer key exactly");
    assert_eq!(
        stats.well_formed_lines, truth.well_formed_lines,
        "well-formed line count must match the answer key exactly"
    );
    assert_eq!(
        stats.malformed_lines, truth.malformed_lines,
        "malformed line count must match the answer key exactly -- corrupted lines must be \
         detected and counted, not silently dropped or silently accepted"
    );
    assert_eq!(
        stats.well_formed_lines + stats.malformed_lines,
        stats.total_lines,
        "every parsed line must be classified as exactly one of well-formed or malformed"
    );
}

#[test]
fn status_class_counts_match_ground_truth_exactly() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    let expected: HashMap<String, u64> = truth.status_class_counts.into_iter().collect();
    assert_eq!(
        stats.status_class_counts, expected,
        "status-class histogram (2xx/3xx/4xx/5xx) over well-formed lines must match the answer \
         key exactly; a degenerate implementation that only tracks one class would fail here \
         since the real corpus has all four"
    );
}

#[test]
fn method_counts_match_ground_truth_exactly() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    let expected: HashMap<String, u64> = truth.method_counts.into_iter().collect();
    assert_eq!(stats.method_counts, expected, "method histogram (GET/POST/PUT/DELETE) must match the answer key exactly");
}

#[test]
fn full_path_histogram_matches_ground_truth_exactly() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    let expected: HashMap<String, u64> = truth.path_counts.into_iter().collect();
    assert_eq!(
        stats.path_counts, expected,
        "the full per-path request histogram (25 distinct paths) must match the answer key \
         exactly; a hardcoded single-entry map would fail immediately"
    );
}

#[test]
fn top_paths_matches_ground_truth_order_and_counts() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    let expected: Vec<(String, u64)> = truth.top_paths.into_iter().map(|pc| (pc.path, pc.count)).collect();
    let actual = top_paths(&stats.path_counts, 10);
    assert_eq!(
        actual, expected,
        "top 10 paths, in descending count order with ascending-path tiebreak, must match the answer key"
    );
}

#[test]
fn unique_ip_count_matches_ground_truth_exactly() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    assert_eq!(
        stats.unique_ips as u64, truth.unique_ips,
        "distinct client IP count over well-formed lines must match the answer key exactly"
    );
}

#[test]
fn error_rate_5xx_matches_ground_truth_within_float_tolerance() {
    let stats = load_stats();
    let truth = ground_truth::load().log;
    assert!(
        (stats.error_rate_5xx - truth.error_rate_5xx).abs() < 1e-9,
        "5xx error rate (fraction of well-formed lines) must match the answer key: expected \
         {}, got {}",
        truth.error_rate_5xx,
        stats.error_rate_5xx
    );
}

#[test]
fn response_time_stats_match_ground_truth_within_tolerance() {
    let stats = load_stats();
    let truth = ground_truth::load().log.response_time_ms;
    let rt = &stats.response_time_stats;
    // 0.1ms tolerance: access.log prints response times rounded to 1 decimal
    // place, so a value parsed from text can differ from the full-precision
    // value the ground truth was computed from by at most ~0.055ms. A wrong
    // percentile/mean implementation would miss by far more than this given
    // how right-skewed this distribution is (p99 is ~4x the mean).
    const TOL: f64 = 0.1;
    assert!(
        (rt.mean_ms - truth.mean_ms).abs() < TOL,
        "mean response time: expected ~{}, got {}",
        truth.mean_ms,
        rt.mean_ms
    );
    assert!((rt.p50_ms - truth.p50_ms).abs() < TOL, "p50 response time: expected ~{}, got {}", truth.p50_ms, rt.p50_ms);
    assert!((rt.p95_ms - truth.p95_ms).abs() < TOL, "p95 response time: expected ~{}, got {}", truth.p95_ms, rt.p95_ms);
    assert!((rt.p99_ms - truth.p99_ms).abs() < TOL, "p99 response time: expected ~{}, got {}", truth.p99_ms, rt.p99_ms);
    assert!((rt.max_ms - truth.max_ms).abs() < TOL, "max response time: expected ~{}, got {}", truth.max_ms, rt.max_ms);
}
