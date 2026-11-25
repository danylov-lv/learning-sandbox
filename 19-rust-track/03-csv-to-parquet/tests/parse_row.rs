//! Unit-level tests for `parse_row` on small, hand-built lines: one
//! well-formed line, and one line per dirty-row corruption mode
//! `sandbox18-datagen` actually produces in `data/products.csv`. None of
//! these touch the real CSV file -- see `ground_truth.rs` for the
//! full-corpus check.

use t03_csv_to_parquet::{parse_row, RowParseError};

const VALID_LINE: &str = "42,SKU-0042,Books,19.99,true,2024-01-15T12:30:00Z";

#[test]
fn parses_a_well_formed_line() {
    let row = parse_row(VALID_LINE).unwrap_or_else(|e| panic!("expected a well-formed line to parse, got error: {e}"));
    assert_eq!(row.id, 42, "id is the first field");
    assert_eq!(row.sku, "SKU-0042", "sku is the second field");
    assert_eq!(row.category, "Books", "category is the third field");
    assert!((row.price - 19.99).abs() < 1e-9, "price should be 19.99, got {}", row.price);
    assert!(row.in_stock, "in_stock should be true for this line");
    assert_eq!(row.scraped_at, "2024-01-15T12:30:00Z", "scraped_at should be stored verbatim");
}

#[test]
fn display_on_any_error_is_non_empty() {
    // Not derived from a specific variant -- only checks Display produces
    // something readable, independent of which corruption triggered it.
    let err = parse_row("not,a,valid,products,csv").expect_err("garbage input must not parse");
    assert!(!err.to_string().is_empty(), "RowParseError's Display must produce a human-readable message");
}

#[test]
fn rejects_wrong_field_count() {
    let err = parse_row("1,SKU-1,Books,9.99,true").expect_err("5 fields instead of 6 must be rejected");
    assert!(
        matches!(err, RowParseError::WrongFieldCount(5)),
        "expected WrongFieldCount(5), got {err:?}"
    );
}

#[test]
fn rejects_empty_sku() {
    let line = VALID_LINE.replace("SKU-0042", "");
    let err = parse_row(&line).expect_err("an empty sku field must be rejected");
    assert!(matches!(err, RowParseError::EmptySku), "expected EmptySku, got {err:?}");
}

#[test]
fn rejects_empty_price() {
    let line = VALID_LINE.replace("19.99", "");
    let err = parse_row(&line).expect_err("an empty price field must be rejected");
    assert!(
        matches!(err, RowParseError::InvalidPrice(_)),
        "an empty price field should fail float parsing, got {err:?}"
    );
}

#[test]
fn rejects_na_price() {
    let line = VALID_LINE.replace("19.99", "N/A");
    let err = parse_row(&line).expect_err("a literal \"N/A\" price field must be rejected");
    assert!(
        matches!(err, RowParseError::InvalidPrice(_)),
        "\"N/A\" should fail float parsing, got {err:?}"
    );
}

#[test]
fn rejects_negative_price() {
    let line = VALID_LINE.replace("19.99", "-19.99");
    let err = parse_row(&line).expect_err("a negative price must be rejected even though it parses as a float");
    match err {
        RowParseError::NonPositivePrice(p) => assert!((p - -19.99).abs() < 1e-9, "expected the offending price -19.99, got {p}"),
        other => panic!("expected NonPositivePrice, got {other:?}"),
    }
}

#[test]
fn rejects_zero_price() {
    let line = VALID_LINE.replace("19.99", "0.00");
    let err = parse_row(&line).expect_err("a zero price is not a positive price and must be rejected");
    assert!(matches!(err, RowParseError::NonPositivePrice(_)), "expected NonPositivePrice, got {err:?}");
}

#[test]
fn rejects_bad_boolean() {
    let line = VALID_LINE.replace("true", "maybe");
    let err = parse_row(&line).expect_err("\"maybe\" is not a valid in_stock literal and must be rejected");
    assert!(matches!(err, RowParseError::InvalidBool(_)), "expected InvalidBool, got {err:?}");
}

#[test]
fn rejects_bad_timestamp() {
    let line = VALID_LINE.replace("2024-01-15T12:30:00Z", "not-a-date");
    let err = parse_row(&line).expect_err("\"not-a-date\" must be rejected as scraped_at");
    assert!(matches!(err, RowParseError::InvalidTimestamp(_)), "expected InvalidTimestamp, got {err:?}");
}

#[test]
fn accepts_in_stock_false() {
    let line = VALID_LINE.replace("true", "false");
    let row = parse_row(&line).unwrap_or_else(|e| panic!("\"false\" is a valid in_stock literal, got error: {e}"));
    assert!(!row.in_stock, "in_stock should be false for this line");
}
