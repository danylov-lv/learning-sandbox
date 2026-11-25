//! Unit-level tests for `parse_log_line` and `status_class` on small,
//! hand-built inputs -- independent of `App`/`handle_event`, which have
//! their own test file. None of these touch `data/access.log`; every
//! expectation here is computed by hand.

use t06_tui_log_dashboard::{parse_log_line, status_class};

const VALID_LINE: &str = "108.204.108.63 - - [01/Jan/2024:00:00:02 +0000] \"GET /api/products HTTP/1.1\" 200 60258 \"-\" \"Mozilla/5.0 (compatible; sandbox18-bot/1.0)\" 18.4";

#[test]
fn parses_method_path_and_status_from_a_well_formed_line() {
    let parsed = parse_log_line(VALID_LINE)
        .unwrap_or_else(|| panic!("expected a well-formed line to parse into Some(ParsedLine)"));
    assert_eq!(parsed.method, "GET", "method is the first token inside the quoted request section");
    assert_eq!(parsed.path, "/api/products", "path is the second token inside the quoted request section");
    assert_eq!(parsed.status, 200, "status is the numeric token right after the closing quote");
}

#[test]
fn parses_a_different_method_and_status_to_rule_out_a_hardcoded_result() {
    let line = "9.9.9.9 - - [01/Jan/2024:00:00:03 +0000] \"POST /api/cart HTTP/1.1\" 500 12 \"-\" \"UA\" 1.0";
    let parsed = parse_log_line(line).unwrap_or_else(|| panic!("expected this well-formed line to parse"));
    assert_eq!(parsed.method, "POST", "must not be hardcoded to \"GET\"");
    assert_eq!(parsed.path, "/api/cart");
    assert_eq!(parsed.status, 500, "must not be hardcoded to 200");
}

#[test]
fn rejects_empty_line() {
    assert!(parse_log_line("").is_none(), "an empty line has no quoted request section and must be rejected");
}

#[test]
fn rejects_whitespace_only_line() {
    assert!(parse_log_line("   \t  ").is_none(), "a whitespace-only line has no quoted request section");
}

#[test]
fn rejects_line_with_no_quotes_at_all() {
    assert!(
        parse_log_line("this is not a log line at all").is_none(),
        "with no '\"' characters there is no request section to extract method/path/status from"
    );
}

#[test]
fn rejects_line_with_quotes_stripped() {
    let corrupted = VALID_LINE.replace('"', "");
    assert!(
        parse_log_line(&corrupted).is_none(),
        "with the quotes removed the request-section boundaries are ambiguous and must not be guessed at"
    );
}

#[test]
fn rejects_request_section_with_missing_tokens() {
    // Only "GET" inside the quotes -- no path, no HTTP version.
    let corrupted = "1.2.3.4 - - [01/Jan/2024:00:00:00 +0000] \"GET\" 200 1 \"-\" \"UA\" 1.0";
    assert!(
        parse_log_line(corrupted).is_none(),
        "a quoted section with fewer than the 3 required tokens (method, path, http-version) must be rejected"
    );
}

#[test]
fn rejects_request_section_with_extra_tokens() {
    let corrupted = "1.2.3.4 - - [01/Jan/2024:00:00:00 +0000] \"GET /x HTTP/1.1 EXTRA\" 200 1 \"-\" \"UA\" 1.0";
    assert!(
        parse_log_line(corrupted).is_none(),
        "a quoted section with an extra 4th token is not the expected \
         \"METHOD PATH HTTP/x.y\" shape and must be rejected, not silently truncated to the first 3"
    );
}

#[test]
fn rejects_path_that_does_not_start_with_a_slash() {
    let corrupted = "1.2.3.4 - - [01/Jan/2024:00:00:00 +0000] \"GET api/products HTTP/1.1\" 200 1 \"-\" \"UA\" 1.0";
    assert!(
        parse_log_line(corrupted).is_none(),
        "a path that doesn't start with '/' does not look like a real request path"
    );
}

#[test]
fn rejects_non_numeric_status_code() {
    let corrupted = VALID_LINE.replacen("200", "UNKNOWN", 1);
    assert!(
        parse_log_line(&corrupted).is_none(),
        "a non-numeric token where the status code belongs must fail to parse as u16, not panic"
    );
}

#[test]
fn rejects_line_truncated_before_the_status_code() {
    // Cut right after the closing quote of the request section.
    let cut_at = VALID_LINE.find("HTTP/1.1\"").expect("fixture must contain the request section") + "HTTP/1.1\"".len();
    let truncated = &VALID_LINE[..cut_at];
    assert!(
        parse_log_line(truncated).is_none(),
        "a line with no status token after the closing quote is missing a required field"
    );
}

#[test]
fn status_class_groups_by_hundreds_digit() {
    assert_eq!(status_class(200), "2xx");
    assert_eq!(status_class(201), "2xx");
    assert_eq!(status_class(301), "3xx");
    assert_eq!(status_class(404), "4xx");
    assert_eq!(status_class(500), "5xx");
    assert_eq!(status_class(503), "5xx");
}

#[test]
fn status_class_covers_more_than_one_class_so_a_constant_return_fails() {
    // A degenerate status_class that always returns e.g. "2xx" passes the
    // first assertion above but fails this one immediately.
    let classes: Vec<&str> = [100u16, 200, 300, 404, 500].iter().map(|&s| status_class(s)).collect();
    assert_eq!(
        classes,
        vec!["1xx", "2xx", "3xx", "4xx", "5xx"],
        "each hundreds-digit must map to its own class label; a constant-returning implementation \
         fails to produce 5 distinct labels here"
    );
}
