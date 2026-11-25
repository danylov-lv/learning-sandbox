//! Shared parquet-reading helpers for this task's tests. Every test reads
//! the Parquet file the learner's code wrote back with `parquet`/`arrow`
//! itself -- never by trusting anything the writer side claims -- so a
//! stub or degenerate writer that produces an empty or wrong-shaped file
//! fails here before any statistic is even computed.
//!
//! Not every helper is used by every test binary that includes this
//! module (each `tests/*.rs` file compiles it separately) -- `dead_code`
//! is allowed here rather than in each caller.
#![allow(dead_code)]

use std::fs::File;
use std::path::Path;

use arrow::array::{Array, BooleanArray, Float64Array, Int64Array, StringArray};
use arrow::datatypes::SchemaRef;
use arrow::record_batch::RecordBatch;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;

/// Reads every record batch out of the Parquet file at `path`, along with
/// its schema. Panics with a clear message on any read failure -- there is
/// no "acceptable" way for a just-written file to fail to open.
pub fn read_all_batches(path: &Path) -> (SchemaRef, Vec<RecordBatch>) {
    let file = File::open(path).unwrap_or_else(|e| panic!("failed to open parquet file {}: {e}", path.display()));
    let builder = ParquetRecordBatchReaderBuilder::try_new(file)
        .unwrap_or_else(|e| panic!("failed to open parquet reader for {}: {e}", path.display()));
    let schema = builder.schema().clone();
    let reader = builder
        .build()
        .unwrap_or_else(|e| panic!("failed to build parquet reader for {}: {e}", path.display()));
    let batches: Vec<RecordBatch> = reader
        .collect::<Result<_, _>>()
        .unwrap_or_else(|e| panic!("failed to read a record batch from {}: {e}", path.display()));
    (schema, batches)
}

/// Concatenates one `Int64` column across every batch, in row order.
pub fn i64_column(batches: &[RecordBatch], name: &str) -> Vec<i64> {
    batches
        .iter()
        .flat_map(|b| {
            let col = b
                .column_by_name(name)
                .unwrap_or_else(|| panic!("no column named {name:?} in the record batch"));
            let arr = col
                .as_any()
                .downcast_ref::<Int64Array>()
                .unwrap_or_else(|| panic!("column {name:?} is not an Int64Array"));
            (0..arr.len()).map(|i| arr.value(i)).collect::<Vec<_>>()
        })
        .collect()
}

/// Concatenates one `Float64` column across every batch, in row order.
pub fn f64_column(batches: &[RecordBatch], name: &str) -> Vec<f64> {
    batches
        .iter()
        .flat_map(|b| {
            let col = b
                .column_by_name(name)
                .unwrap_or_else(|| panic!("no column named {name:?} in the record batch"));
            let arr = col
                .as_any()
                .downcast_ref::<Float64Array>()
                .unwrap_or_else(|| panic!("column {name:?} is not a Float64Array"));
            (0..arr.len()).map(|i| arr.value(i)).collect::<Vec<_>>()
        })
        .collect()
}

/// Concatenates one `Boolean` column across every batch, in row order.
pub fn bool_column(batches: &[RecordBatch], name: &str) -> Vec<bool> {
    batches
        .iter()
        .flat_map(|b| {
            let col = b
                .column_by_name(name)
                .unwrap_or_else(|| panic!("no column named {name:?} in the record batch"));
            let arr = col
                .as_any()
                .downcast_ref::<BooleanArray>()
                .unwrap_or_else(|| panic!("column {name:?} is not a BooleanArray"));
            (0..arr.len()).map(|i| arr.value(i)).collect::<Vec<_>>()
        })
        .collect()
}

/// Concatenates one `Utf8` column across every batch, in row order.
pub fn string_column(batches: &[RecordBatch], name: &str) -> Vec<String> {
    batches
        .iter()
        .flat_map(|b| {
            let col = b
                .column_by_name(name)
                .unwrap_or_else(|| panic!("no column named {name:?} in the record batch"));
            let arr = col
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap_or_else(|| panic!("column {name:?} is not a StringArray"));
            (0..arr.len()).map(|i| arr.value(i).to_string()).collect::<Vec<_>>()
        })
        .collect()
}

/// Total row count across every batch.
pub fn total_rows(batches: &[RecordBatch]) -> usize {
    batches.iter().map(RecordBatch::num_rows).sum()
}
