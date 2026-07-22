//! Small, hand-built CSV -> Parquet round trip with expectations computed
//! by hand (never by re-running the learner's own code a second way).
//! Deliberately uses two categories with different price stats, and a mix
//! of every dirty-row corruption mode `data/products.csv` actually
//! contains, so a stub or degenerate writer (an empty file, a single
//! hardcoded row, or a writer that ignores category/price entirely) fails
//! here independent of the full-corpus check in `ground_truth.rs`.

mod common;

use std::io::Write;

use t03_csv_to_parquet::write_products_parquet;

/// 9 data lines: 4 valid (2 Books, 2 Toys, with different prices so the
/// two categories' stats differ), 5 dirty (one per corruption mode this
/// module's data generator actually produces).
const CSV_BODY: &str = concat!(
    "id,sku,category,price,in_stock,scraped_at\n",
    "1,SKU-1,Books,10.00,true,2024-01-01T00:00:00Z\n",
    "2,SKU-2,Books,20.00,false,2024-01-02T00:00:00Z\n",
    "3,SKU-3,Toys,5.00,true,2024-01-03T00:00:00Z\n",
    "4,SKU-4,Toys,15.00,true,2024-01-04T00:00:00Z\n",
    "5,,Toys,8.00,true,2024-01-05T00:00:00Z\n",
    "6,SKU-6,Books,-3.00,true,2024-01-06T00:00:00Z\n",
    "7,SKU-7,Books,N/A,true,2024-01-07T00:00:00Z\n",
    "8,SKU-8,Toys,12.00,maybe,2024-01-08T00:00:00Z\n",
    "9,SKU-9,Toys,9.00,false,not-a-date\n",
);

fn write_fixture_and_convert(row_group_size: usize) -> (tempfile::TempDir, std::path::PathBuf) {
    let dir = tempfile::tempdir().expect("create scratch dir");
    let csv_path = dir.path().join("fixture.csv");
    let parquet_path = dir.path().join("fixture.parquet");
    let mut f = std::fs::File::create(&csv_path).expect("create fixture csv");
    f.write_all(CSV_BODY.as_bytes()).expect("write fixture csv");
    drop(f);

    let stats = write_products_parquet(&csv_path, &parquet_path, row_group_size)
        .unwrap_or_else(|e| panic!("write_products_parquet failed on the hand-built fixture: {e}"));

    assert_eq!(stats.total_rows, 9, "9 data lines (excluding the header) were written to the fixture");
    assert_eq!(stats.valid_rows, 4, "4 of the 9 lines are valid: two Books, two Toys");
    assert_eq!(
        stats.dirty_rows, 5,
        "5 lines are dirty: empty sku, negative price, N/A price, bad boolean, bad timestamp"
    );
    assert_eq!(
        stats.valid_rows + stats.dirty_rows,
        stats.total_rows,
        "every counted data row must be classified as exactly one of valid or dirty"
    );

    (dir, parquet_path)
}

#[test]
fn row_count_and_dtypes_match_the_intended_schema() {
    let (_dir, parquet_path) = write_fixture_and_convert(1_000);
    let (schema, batches) = common::read_all_batches(&parquet_path);

    assert_eq!(
        common::total_rows(&batches),
        4,
        "only the 4 valid rows should make it into the Parquet file -- dirty rows must be dropped, not written"
    );

    use arrow::datatypes::DataType;
    let expect_type = |name: &str, expected: DataType| {
        let field = schema
            .field_with_name(name)
            .unwrap_or_else(|_| panic!("expected a column named {name:?} in the written schema"));
        assert_eq!(
            field.data_type(),
            &expected,
            "column {name:?} should be written as {expected:?}, got {:?}",
            field.data_type()
        );
    };
    expect_type("id", DataType::Int64);
    expect_type("sku", DataType::Utf8);
    expect_type("category", DataType::Utf8);
    expect_type("price", DataType::Float64);
    expect_type("in_stock", DataType::Boolean);
    expect_type("scraped_at", DataType::Utf8);
}

#[test]
fn dirty_rows_are_excluded_and_valid_values_are_written_correctly() {
    let (_dir, parquet_path) = write_fixture_and_convert(1_000);
    let (_schema, batches) = common::read_all_batches(&parquet_path);

    let mut ids = common::i64_column(&batches, "id");
    ids.sort_unstable();
    assert_eq!(
        ids,
        vec![1, 2, 3, 4],
        "only ids 1-4 (the valid rows) should be present; ids 5-9 (the dirty rows) must be excluded"
    );
}

#[test]
fn per_category_and_overall_price_stats_match_hand_computed_expectations() {
    // A writer forced through row groups of 2 must still produce the same
    // aggregate answer as one big row group -- proves row-group splitting
    // doesn't silently drop or duplicate rows.
    let (_dir, parquet_path) = write_fixture_and_convert(2);
    let (_schema, batches) = common::read_all_batches(&parquet_path);

    let categories = common::string_column(&batches, "category");
    let prices = common::f64_column(&batches, "price");
    let in_stock = common::bool_column(&batches, "in_stock");

    let books_prices: Vec<f64> = categories
        .iter()
        .zip(&prices)
        .filter(|(c, _)| c.as_str() == "Books")
        .map(|(_, p)| *p)
        .collect();
    let toys_prices: Vec<f64> = categories
        .iter()
        .zip(&prices)
        .filter(|(c, _)| c.as_str() == "Toys")
        .map(|(_, p)| *p)
        .collect();

    assert_eq!(books_prices.len(), 2, "exactly 2 valid Books rows (ids 1, 2)");
    assert_eq!(toys_prices.len(), 2, "exactly 2 valid Toys rows (ids 3, 4)");

    let sum = |v: &[f64]| v.iter().sum::<f64>();
    let mean = |v: &[f64]| sum(v) / v.len() as f64;

    // Books: 10.00, 20.00 -- Toys: 5.00, 15.00. Deliberately different
    // means (15.0 vs 10.0): a writer that collapses every row into one
    // category, or reports the same stats regardless of category, fails
    // this comparison even though row counts might still look right.
    assert!((sum(&books_prices) - 30.0).abs() < 1e-9, "Books prices should sum to 30.0, got {}", sum(&books_prices));
    assert!((mean(&books_prices) - 15.0).abs() < 1e-9, "Books mean price should be 15.0, got {}", mean(&books_prices));
    assert!((sum(&toys_prices) - 20.0).abs() < 1e-9, "Toys prices should sum to 20.0, got {}", sum(&toys_prices));
    assert!((mean(&toys_prices) - 10.0).abs() < 1e-9, "Toys mean price should be 10.0, got {}", mean(&toys_prices));

    let overall_sum = sum(&prices);
    let overall_mean = mean(&prices);
    assert!((overall_sum - 50.0).abs() < 1e-9, "overall price sum across all 4 valid rows should be 50.0, got {overall_sum}");
    assert!((overall_mean - 12.5).abs() < 1e-9, "overall mean price should be 12.5, got {overall_mean}");
    let overall_min = prices.iter().cloned().fold(f64::INFINITY, f64::min);
    let overall_max = prices.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    assert!((overall_min - 5.0).abs() < 1e-9, "overall min price should be 5.0 (Toys row 3), got {overall_min}");
    assert!((overall_max - 20.0).abs() < 1e-9, "overall max price should be 20.0 (Books row 2), got {overall_max}");

    let in_stock_count = in_stock.iter().filter(|b| **b).count();
    let out_of_stock_count = in_stock.iter().filter(|b| !**b).count();
    assert_eq!(
        in_stock_count, 3,
        "3 of the 4 valid rows have in_stock=true (ids 1, 3, 4); a writer that ignores in_stock would not reproduce this 3-1 split"
    );
    assert_eq!(out_of_stock_count, 1, "exactly 1 of the 4 valid rows (id 2) has in_stock=false");
}
