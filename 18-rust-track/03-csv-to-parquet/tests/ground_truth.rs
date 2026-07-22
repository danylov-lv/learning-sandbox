//! Full-corpus check: converts the real `data/products.csv` and compares
//! the written Parquet file against `data/ground-truth.json`, loaded
//! through the harness -- never against a second computation of the
//! learner's own code. Run `cargo run -p sandbox18-datagen` from the
//! module root first if this fails to find the data file.
//!
//! Money tolerance: `mean`/`sum` in the ground truth were rounded to the
//! nearest cent at generation time, and floating-point summation over
//! ~490k values accumulates its own (much smaller) rounding error, so
//! those two are compared with a small absolute tolerance rather than
//! exact equality. `min`/`max` are literal values that appeared in the
//! data, so those are checked far tighter.

mod common;

use std::collections::BTreeMap;

use sandbox18_harness::ground_truth;
use t03_csv_to_parquet::write_products_parquet;

const MEAN_SUM_TOL: f64 = 0.05;
const MIN_MAX_TOL: f64 = 1e-6;

struct Converted {
    _dir: tempfile::TempDir,
    parquet_path: std::path::PathBuf,
    stats: t03_csv_to_parquet::ConversionStats,
}

fn convert_real_csv() -> Converted {
    let csv_path = ground_truth::data_path("products.csv");
    let dir = tempfile::tempdir().expect("create scratch dir");
    let parquet_path = dir.path().join("products.parquet");

    let stats = write_products_parquet(&csv_path, &parquet_path, 50_000).unwrap_or_else(|e| {
        panic!(
            "write_products_parquet failed on the real data file {}: {e}\n\
             hint: run `cargo run -p sandbox18-datagen` from the module root first",
            csv_path.display()
        )
    });

    Converted {
        _dir: dir,
        parquet_path,
        stats,
    }
}

#[test]
fn row_counts_match_ground_truth_exactly() {
    let converted = convert_real_csv();
    let truth = ground_truth::load().csv;

    assert_eq!(
        converted.stats.total_rows, truth.total_rows,
        "total data-row count (excluding the header) must match the answer key exactly"
    );
    assert_eq!(
        converted.stats.valid_rows, truth.valid_rows,
        "valid-row count must match the answer key exactly"
    );
    assert_eq!(
        converted.stats.dirty_rows, truth.dirty_rows,
        "dirty-row count must match the answer key exactly -- corrupted rows must be detected \
         and counted, not silently dropped or silently accepted"
    );
    assert_eq!(
        converted.stats.valid_rows + converted.stats.dirty_rows,
        converted.stats.total_rows,
        "every data row must be classified as exactly one of valid or dirty"
    );

    let (_schema, batches) = common::read_all_batches(&converted.parquet_path);
    assert_eq!(
        common::total_rows(&batches) as u64,
        truth.valid_rows,
        "the Parquet file itself must contain exactly one row per valid CSV row -- a writer that \
         drops rows across row-group boundaries, or that writes dirty rows too, fails here even \
         if the returned ConversionStats looked right"
    );
}

#[test]
fn column_dtypes_match_the_intended_schema() {
    let converted = convert_real_csv();
    let (schema, _batches) = common::read_all_batches(&converted.parquet_path);

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
fn in_stock_and_out_of_stock_counts_match_ground_truth_exactly() {
    let converted = convert_real_csv();
    let truth = ground_truth::load().csv;
    let (_schema, batches) = common::read_all_batches(&converted.parquet_path);

    let in_stock = common::bool_column(&batches, "in_stock");
    let in_stock_count = in_stock.iter().filter(|b| **b).count() as u64;
    let out_of_stock_count = in_stock.iter().filter(|b| !**b).count() as u64;

    assert_eq!(
        in_stock_count, truth.in_stock_count,
        "in_stock=true count among valid rows must match the answer key exactly"
    );
    assert_eq!(
        out_of_stock_count, truth.out_of_stock_count,
        "in_stock=false count among valid rows must match the answer key exactly"
    );
}

#[test]
fn category_counts_match_ground_truth_exactly() {
    let converted = convert_real_csv();
    let truth = ground_truth::load().csv;
    let (_schema, batches) = common::read_all_batches(&converted.parquet_path);

    let categories = common::string_column(&batches, "category");
    let mut counts: BTreeMap<String, u64> = BTreeMap::new();
    for c in categories {
        *counts.entry(c).or_insert(0) += 1;
    }

    assert_eq!(
        counts, truth.category_counts,
        "per-category row counts over valid rows must match the answer key exactly -- a writer \
         that hardcodes or collapses categories fails here since the real data has 12 distinct \
         categories with very different counts"
    );
}

#[test]
fn overall_price_stats_match_ground_truth_within_tolerance() {
    let converted = convert_real_csv();
    let truth = ground_truth::load().csv.overall_price_stats;
    let (_schema, batches) = common::read_all_batches(&converted.parquet_path);

    let prices = common::f64_column(&batches, "price");
    let count = prices.len() as u64;
    let sum: f64 = prices.iter().sum();
    let mean = sum / prices.len() as f64;
    let min = prices.iter().cloned().fold(f64::INFINITY, f64::min);
    let max = prices.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    assert_eq!(count, truth.count, "overall valid price count must match the answer key exactly, got {count} vs {}", truth.count);
    assert!((min - truth.min).abs() < MIN_MAX_TOL, "overall min price: expected {}, got {min}", truth.min);
    assert!((max - truth.max).abs() < MIN_MAX_TOL, "overall max price: expected {}, got {max}", truth.max);
    assert!(
        (mean - truth.mean).abs() < MEAN_SUM_TOL,
        "overall mean price: expected ~{}, got {mean} (tolerance {MEAN_SUM_TOL})",
        truth.mean
    );
    assert!(
        (sum - truth.sum).abs() < MEAN_SUM_TOL,
        "overall price sum: expected ~{}, got {sum} (tolerance {MEAN_SUM_TOL})",
        truth.sum
    );
}

#[test]
fn per_category_price_stats_match_ground_truth_within_tolerance() {
    let converted = convert_real_csv();
    let truth = ground_truth::load().csv;
    let (_schema, batches) = common::read_all_batches(&converted.parquet_path);

    let categories = common::string_column(&batches, "category");
    let prices = common::f64_column(&batches, "price");

    let mut by_category: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    for (c, p) in categories.into_iter().zip(prices) {
        by_category.entry(c).or_default().push(p);
    }

    assert_eq!(
        by_category.len(),
        truth.category_price_stats.len(),
        "expected stats for all {} categories present in the answer key, got {}",
        truth.category_price_stats.len(),
        by_category.len()
    );

    // Checking more than one category, on more than one field, is what
    // catches a writer that reports the same (or a hardcoded) stats blob
    // for every category regardless of its actual rows.
    for (category, truth_stats) in &truth.category_price_stats {
        let values = by_category
            .get(category)
            .unwrap_or_else(|| panic!("category {category:?} from the answer key is missing entirely from the written Parquet file"));

        let count = values.len() as u64;
        let sum: f64 = values.iter().sum();
        let mean = sum / values.len() as f64;
        let min = values.iter().cloned().fold(f64::INFINITY, f64::min);
        let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        assert_eq!(count, truth_stats.count, "category {category:?}: expected {} rows, got {count}", truth_stats.count);
        assert!(
            (min - truth_stats.min).abs() < MIN_MAX_TOL,
            "category {category:?}: expected min {}, got {min}",
            truth_stats.min
        );
        assert!(
            (max - truth_stats.max).abs() < MIN_MAX_TOL,
            "category {category:?}: expected max {}, got {max}",
            truth_stats.max
        );
        assert!(
            (mean - truth_stats.mean).abs() < MEAN_SUM_TOL,
            "category {category:?}: expected mean ~{}, got {mean}",
            truth_stats.mean
        );
        assert!(
            (sum - truth_stats.sum).abs() < MEAN_SUM_TOL,
            "category {category:?}: expected sum ~{}, got {sum}",
            truth_stats.sum
        );
    }
}
