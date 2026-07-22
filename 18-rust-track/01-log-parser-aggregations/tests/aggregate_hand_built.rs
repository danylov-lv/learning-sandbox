//! Integration tests over small, hand-built log corpora with expectations
//! computed by hand (never by re-running the learner's own code a second
//! way). These pin down the exact semantics -- percentile formula, top-path
//! tie-breaking, empty-input behavior -- on inputs small enough to verify
//! by eye, independent of the full-corpus check against
//! `data/ground-truth.json` in `aggregate_ground_truth.rs`.

use std::collections::HashMap;
use std::io::{BufReader, Cursor};

use t01_log_parser_aggregations::{aggregate, percentile, top_paths};

/// 6 well-formed lines (2 status classes each covered at least once, 3
/// distinct methods, 3 distinct paths, 4 distinct IPs) + 2 malformed lines.
/// Response times are 10.0, 20.0, .., 60.0 -- round numbers chosen so mean
/// and percentiles can be checked by hand.
const CORPUS: &str = concat!(
    "10.0.0.1 - - [01/Jan/2024:00:00:00 +0000] \"GET / HTTP/1.1\" 200 100 \"-\" \"UA\" 10.0\n",
    "10.0.0.2 - - [01/Jan/2024:00:00:01 +0000] \"GET /api HTTP/1.1\" 200 200 \"-\" \"UA\" 20.0\n",
    "10.0.0.1 - - [01/Jan/2024:00:00:02 +0000] \"POST /api HTTP/1.1\" 500 300 \"-\" \"UA\" 30.0\n",
    "10.0.0.3 - - [01/Jan/2024:00:00:03 +0000] \"GET / HTTP/1.1\" 404 400 \"-\" \"UA\" 40.0\n",
    "10.0.0.4 - - [01/Jan/2024:00:00:04 +0000] \"PUT /api/cart HTTP/1.1\" 301 500 \"-\" \"UA\" 50.0\n",
    "10.0.0.2 - - [01/Jan/2024:00:00:05 +0000] \"DELETE /api HTTP/1.1\" 200 600 \"-\" \"UA\" 60.0\n",
    "this is not a log line at all\n",
    "10.0.0.5 - - 01/Jan/2024:00:00:06 +0000 \"GET /health HTTP/1.1\" 200 100 \"-\" \"UA\" 5.0\n",
);

fn reader_over(text: &str) -> BufReader<Cursor<&[u8]>> {
    BufReader::new(Cursor::new(text.as_bytes()))
}

#[test]
fn counts_total_well_formed_and_malformed_lines() {
    let stats = aggregate(reader_over(CORPUS));
    assert_eq!(
        stats.well_formed_lines + stats.malformed_lines,
        stats.total_lines,
        "every line must be counted as exactly one of well-formed or malformed, no line dropped \
         and none double-counted"
    );
    assert_eq!(stats.total_lines, 8, "the corpus has exactly 8 lines");
    assert_eq!(stats.well_formed_lines, 6, "6 of the 8 lines are well-formed");
    assert_eq!(stats.malformed_lines, 2, "2 of the 8 lines are corrupted (no log line at all, and missing brackets)");
}

#[test]
fn status_class_counts_match_hand_computed_expectation() {
    let stats = aggregate(reader_over(CORPUS));
    let expected: HashMap<String, u64> = [("2xx".to_string(), 3), ("3xx".to_string(), 1), ("4xx".to_string(), 1), ("5xx".to_string(), 1)]
        .into_iter()
        .collect();
    assert_eq!(
        stats.status_class_counts, expected,
        "3 lines are 2xx (two 200s + one more 200), 1 is 3xx (301), 1 is 4xx (404), 1 is 5xx (500)"
    );
}

#[test]
fn method_counts_match_hand_computed_expectation() {
    let stats = aggregate(reader_over(CORPUS));
    let expected: HashMap<String, u64> = [
        ("GET".to_string(), 3),
        ("POST".to_string(), 1),
        ("PUT".to_string(), 1),
        ("DELETE".to_string(), 1),
    ]
    .into_iter()
    .collect();
    assert_eq!(stats.method_counts, expected, "3 GETs, 1 each of POST/PUT/DELETE among the 6 well-formed lines");
}

#[test]
fn path_counts_match_hand_computed_expectation() {
    let stats = aggregate(reader_over(CORPUS));
    let expected: HashMap<String, u64> =
        [("/".to_string(), 2), ("/api".to_string(), 3), ("/api/cart".to_string(), 1)].into_iter().collect();
    assert_eq!(stats.path_counts, expected, "\"/\" appears twice, \"/api\" three times, \"/api/cart\" once");
}

#[test]
fn unique_ips_counts_distinct_client_addresses() {
    let stats = aggregate(reader_over(CORPUS));
    assert_eq!(
        stats.unique_ips, 4,
        "10.0.0.1, 10.0.0.2, 10.0.0.3, 10.0.0.4 are the 4 distinct IPs among well-formed lines \
         (10.0.0.5 is on the malformed line and must not be counted)"
    );
}

#[test]
fn error_rate_5xx_is_fraction_of_well_formed_lines() {
    let stats = aggregate(reader_over(CORPUS));
    let expected = 1.0 / 6.0;
    assert!(
        (stats.error_rate_5xx - expected).abs() < 1e-9,
        "1 of the 6 well-formed lines is a 5xx (the 500), so error_rate_5xx should be {expected}, got {}",
        stats.error_rate_5xx
    );
}

#[test]
fn response_time_stats_match_hand_computed_percentiles() {
    let stats = aggregate(reader_over(CORPUS));
    let rt = &stats.response_time_stats;
    // Well-formed response times: 10, 20, 30, 40, 50, 60 (sorted ascending, n=6).
    assert!((rt.mean_ms - 35.0).abs() < 1e-9, "mean of 10..60 step 10 is 35.0, got {}", rt.mean_ms);
    assert!(
        (rt.p50_ms - 40.0).abs() < 1e-9,
        "nearest-rank p50 on a 6-element sorted array is index round(0.5*5)=3 -> 40.0, got {}",
        rt.p50_ms
    );
    assert!(
        (rt.p95_ms - 60.0).abs() < 1e-9,
        "nearest-rank p95 on a 6-element sorted array is index round(0.95*5)=5 -> 60.0, got {}",
        rt.p95_ms
    );
    assert!(
        (rt.p99_ms - 60.0).abs() < 1e-9,
        "nearest-rank p99 on a 6-element sorted array is index round(0.99*5)=5 -> 60.0, got {}",
        rt.p99_ms
    );
    assert!((rt.max_ms - 60.0).abs() < 1e-9, "max response time in the corpus is 60.0, got {}", rt.max_ms);
}

#[test]
fn top_paths_over_the_corpus_orders_by_count_descending() {
    let stats = aggregate(reader_over(CORPUS));
    let top = top_paths(&stats.path_counts, 10);
    let expected = vec![("/api".to_string(), 3), ("/".to_string(), 2), ("/api/cart".to_string(), 1)];
    assert_eq!(top, expected, "top_paths must sort by count descending with no ties in this corpus");
}

#[test]
fn aggregate_over_empty_input_is_all_zero_not_a_panic() {
    let stats = aggregate(reader_over(""));
    assert_eq!(stats.total_lines, 0, "an empty reader has zero lines");
    assert_eq!(stats.well_formed_lines, 0);
    assert_eq!(stats.malformed_lines, 0);
    assert!(stats.status_class_counts.is_empty(), "no lines means no status classes observed");
    assert!(stats.path_counts.is_empty(), "no lines means no paths observed");
    assert_eq!(stats.unique_ips, 0);
    assert_eq!(stats.error_rate_5xx, 0.0, "error rate over zero well-formed lines must not be NaN or panic from a 0/0 division");
    assert_eq!(stats.response_time_stats.mean_ms, 0.0, "response-time stats over zero samples must be 0.0, not NaN");
}

#[test]
fn percentile_matches_nearest_rank_formula_on_a_hand_built_array() {
    let sorted = [1.0, 2.0, 3.0, 4.0, 5.0];
    assert_eq!(percentile(&sorted, 0.50), 3.0, "round(0.50 * 4) = 2 -> sorted[2] = 3.0");
    assert_eq!(percentile(&sorted, 0.95), 5.0, "round(0.95 * 4) = 4 -> sorted[4] = 5.0");
    assert_eq!(percentile(&sorted, 0.99), 5.0, "round(0.99 * 4) = 4 -> sorted[4] = 5.0");
    assert_eq!(percentile(&[], 0.50), 0.0, "percentile of an empty slice must be 0.0, not a panic");
}

#[test]
fn top_paths_breaks_ties_by_path_name_ascending() {
    let counts: HashMap<String, u64> =
        [("/".to_string(), 2), ("/api".to_string(), 2), ("/zzz".to_string(), 1)].into_iter().collect();
    let top = top_paths(&counts, 10);
    let expected = vec![("/".to_string(), 2), ("/api".to_string(), 2), ("/zzz".to_string(), 1)];
    assert_eq!(
        top, expected,
        "\"/\" and \"/api\" tie on count 2 and must be ordered by path name ascending (\"/\" < \"/api\" \
         since \"/\" is a prefix of \"/api\"); \"/zzz\" trails with count 1"
    );
}

#[test]
fn top_paths_truncates_to_n() {
    let counts: HashMap<String, u64> = [
        ("/a".to_string(), 5),
        ("/b".to_string(), 4),
        ("/c".to_string(), 3),
        ("/d".to_string(), 2),
        ("/e".to_string(), 1),
    ]
    .into_iter()
    .collect();
    let top = top_paths(&counts, 2);
    assert_eq!(
        top,
        vec![("/a".to_string(), 5), ("/b".to_string(), 4)],
        "top_paths(_, 2) must return only the 2 highest-count entries, not the full histogram"
    );
}
