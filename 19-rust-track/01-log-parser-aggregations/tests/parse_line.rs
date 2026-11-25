//! Unit-level tests for `parse_line` on small, hand-built inputs: one
//! well-formed line per corruption mode `sandbox18-datagen` actually
//! produces, plus edge cases (empty input, whitespace only). None of these
//! touch `data/access.log` — they must pass on their own hand-computed
//! expectations, independent of the full-corpus test in
//! `aggregate_ground_truth.rs`.

use t01_log_parser_aggregations::{parse_line, LogParseError};

const VALID_LINE: &str = "108.204.108.63 - - [01/Jan/2024:00:00:02 +0000] \"GET /api/products HTTP/1.1\" 200 60258 \"-\" \"Mozilla/5.0 (compatible; sandbox18-bot/1.0)\" 18.4";

#[test]
fn parses_a_well_formed_line() {
    let entry = parse_line(VALID_LINE)
        .unwrap_or_else(|e| panic!("expected a well-formed line to parse, got error: {e}"));

    assert_eq!(entry.ip, "108.204.108.63", "ip should be the first whitespace-separated field");
    assert_eq!(
        entry.timestamp, "01/Jan/2024:00:00:02 +0000",
        "timestamp should be the raw text between the [ and ] brackets, unparsed"
    );
    assert_eq!(entry.method, "GET", "method is the first token inside the quoted request line");
    assert_eq!(entry.path, "/api/products", "path is the second token inside the quoted request line");
    assert_eq!(entry.status, 200, "status is the field right after the closing quote of the request line");
    assert_eq!(entry.bytes, 60258, "bytes is the field right after the status code");
    assert!(
        (entry.response_time_ms - 18.4).abs() < 1e-9,
        "response_time_ms should be the final bare field on the line, got {}",
        entry.response_time_ms
    );
}

#[test]
fn well_formed_line_produces_non_empty_display_on_a_manually_built_error() {
    // Not derived from parse_line -- this only checks that *some* malformed
    // input produces a readable message, independent of which variant it is.
    let err = parse_line("not a log line at all")
        .expect_err("a line with none of the expected structure must not parse successfully");
    let message = err.to_string();
    assert!(
        !message.is_empty(),
        "Display for LogParseError must produce a human-readable message, got an empty string"
    );
}

#[test]
fn rejects_empty_line() {
    assert!(parse_line("").is_err(), "an empty line has none of the required fields and must be rejected");
}

#[test]
fn rejects_whitespace_only_line() {
    assert!(
        parse_line("   \t  ").is_err(),
        "a whitespace-only line has none of the required fields and must be rejected"
    );
}

#[test]
fn rejects_line_with_brackets_stripped() {
    // Corruption mode 0 in sandbox18-datagen: removes '[' and ']' around the timestamp.
    let corrupted = VALID_LINE.replace('[', "").replace(']', "");
    assert!(
        parse_line(&corrupted).is_err(),
        "a timestamp with no [ ] delimiters must be rejected, not parsed with a guessed boundary"
    );
}

#[test]
fn rejects_line_with_non_numeric_status() {
    // Corruption mode 1: the status code is replaced with the literal text "UNKNOWN".
    let corrupted = VALID_LINE.replacen("200", "UNKNOWN", 1);
    let err = parse_line(&corrupted)
        .expect_err("a non-numeric status code must fail to parse as an integer");
    assert!(
        matches!(err, LogParseError::InvalidInteger(_)),
        "a non-numeric status token should surface as LogParseError::InvalidInteger via `?` and \
         the ParseIntError -> LogParseError From conversion, got {err:?}"
    );
}

#[test]
fn rejects_truncated_line() {
    // Corruption mode 2: the line is cut in half mid-record.
    let cut = &VALID_LINE[..VALID_LINE.len() / 2];
    assert!(
        parse_line(cut).is_err(),
        "a line truncated mid-record is missing required trailing fields and must be rejected"
    );
}

#[test]
fn rejects_line_with_quotes_stripped() {
    // Corruption mode 3: every '"' character is removed.
    let corrupted = VALID_LINE.replace('"', "");
    assert!(
        parse_line(&corrupted).is_err(),
        "with no quotes to delimit the request line and user-agent, the field boundaries are \
         ambiguous and the line must be rejected rather than guessed at"
    );
}

#[test]
fn rejects_line_with_trailing_garbage() {
    // Corruption mode 4: an unexpected extra token is appended at the end.
    let corrupted = format!("{VALID_LINE} EXTRA_GARBAGE_FIELD");
    assert!(
        parse_line(&corrupted).is_err(),
        "an extra trailing token corrupts the final (response-time) field and must be rejected, \
         not silently truncated back to a valid-looking number"
    );
}
