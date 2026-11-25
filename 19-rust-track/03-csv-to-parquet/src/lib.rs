//! t03-csv-to-parquet.
//!
//! Reads `data/products.csv` (`id,sku,category,price,in_stock,scraped_at`,
//! ~2% dirty rows) and writes the valid rows out as a single Parquet file
//! via `arrow`/`parquet` -- no `csv` crate: every category and sku value in
//! the real data is comma-free, so a hand-rolled `split(',')` is exact, the
//! same choice task 01 made for its log lines. See README.md for the exact
//! dirty-row rules and the Parquet schema this must produce; `tests/` is
//! the validator.
//!
//! ## The header line
//!
//! `data/products.csv` has one header line (`id,sku,category,price,in_stock,
//! scraped_at`). Callers of [`write_products_parquet`] never see it handled
//! specially inside [`parse_row`] / [`parse_rows`] -- those two only ever
//! see data lines. Skipping exactly the first line of the file, always and
//! unconditionally, is [`write_products_parquet`]'s job, not something
//! [`parse_row`] re-detects by guessing "does this look like a header".

use std::fmt;
use std::io::BufRead;
use std::num::{ParseFloatError, ParseIntError};
use std::path::Path;

use arrow::array::{ArrayBuilder, ArrayRef, BooleanBuilder, Float64Builder, Int64Builder, StringBuilder};
use arrow::datatypes::{DataType, Field};
use arrow::error::ArrowError;
use parquet::errors::ParquetError;

/// One valid, fully-parsed row of `products.csv`.
#[derive(Debug, Clone, PartialEq)]
pub struct ProductRow {
    pub id: i64,
    pub sku: String,
    pub category: String,
    pub price: f64,
    pub in_stock: bool,
    /// Raw `YYYY-MM-DDTHH:MM:SSZ` text, stored verbatim -- this task does
    /// not parse it into a timestamp type, only validates its shape.
    pub scraped_at: String,
}

/// Everything that can be wrong with one CSV data line. Every dirty-row
/// corruption mode `sandbox18-datagen` produces maps to exactly one of
/// these; a row that fails for more than one reason still only reports the
/// first one `parse_row` happens to check.
#[derive(Debug)]
pub enum RowParseError {
    /// The line didn't split into exactly 6 comma-separated fields.
    WrongFieldCount(usize),
    /// The `id` field did not parse as an integer.
    InvalidId(ParseIntError),
    /// The `sku` field was empty.
    EmptySku,
    /// The `price` field did not parse as a float at all (empty, `"N/A"`, ...).
    InvalidPrice(ParseFloatError),
    /// The `price` field parsed fine but was not a positive number.
    NonPositivePrice(f64),
    /// The `in_stock` field was neither the literal `"true"` nor `"false"`.
    InvalidBool(String),
    /// The `scraped_at` field did not match `YYYY-MM-DDTHH:MM:SSZ`.
    InvalidTimestamp(String),
}

impl fmt::Display for RowParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RowParseError::WrongFieldCount(n) => {
                write!(f, "expected 6 comma-separated fields, found {n}")
            }
            RowParseError::InvalidId(e) => write!(f, "invalid id: {e}"),
            RowParseError::EmptySku => write!(f, "sku field is empty"),
            RowParseError::InvalidPrice(e) => write!(f, "invalid price: {e}"),
            RowParseError::NonPositivePrice(p) => write!(f, "price must be positive, got {p}"),
            RowParseError::InvalidBool(s) => {
                write!(f, "in_stock must be \"true\" or \"false\", got {s:?}")
            }
            RowParseError::InvalidTimestamp(s) => {
                write!(f, "scraped_at does not match YYYY-MM-DDTHH:MM:SSZ, got {s:?}")
            }
        }
    }
}

impl std::error::Error for RowParseError {}

impl From<ParseIntError> for RowParseError {
    fn from(err: ParseIntError) -> Self {
        RowParseError::InvalidId(err)
    }
}

impl From<ParseFloatError> for RowParseError {
    fn from(err: ParseFloatError) -> Self {
        RowParseError::InvalidPrice(err)
    }
}

/// `true` iff `s` matches the fixed shape `YYYY-MM-DDTHH:MM:SSZ` (4-2-2
/// digit date, `T`, 2:2:2 digit time, trailing `Z`) with every "letter"
/// position holding an ASCII digit. Not a general ISO-8601 validator --
/// this task only ever needs to reject `sandbox18-datagen`'s one corrupted
/// shape (`"not-a-date"`), not validate arbitrary timestamp dialects.
fn looks_like_timestamp(s: &str) -> bool {
    todo!(
        "check s.as_bytes().len() == 20, and that the 4 'letter' positions ('-', '-', 'T', ':', \
         ':', 'Z' at byte offsets 4, 7, 10, 13, 16, 19) hold exactly those bytes, with every \
         other position an ASCII digit (u8::is_ascii_digit)"
    )
}

/// Parses one CSV data line (never the header) into a [`ProductRow`], or
/// reports the first thing wrong with it as a [`RowParseError`]. Never
/// panics on malformed input, never returns a best-guess row.
pub fn parse_row(line: &str) -> Result<ProductRow, RowParseError> {
    todo!(
        "line.split(',').collect() into exactly 6 fields (else WrongFieldCount); parse id with \
         `?` (ParseIntError converts via From); reject an empty sku; parse price with `?` then \
         reject <= 0.0 as NonPositivePrice; match in_stock against \"true\"/\"false\" exactly, \
         else InvalidBool; validate scraped_at with looks_like_timestamp, else \
         InvalidTimestamp; build the ProductRow last, once every field is known good"
    )
}

/// Streams the data lines of `reader` (the header must already be consumed
/// by the caller) into `Result<ProductRow, RowParseError>`, one per line,
/// in order -- never buffering the whole input into a `Vec` up front, and
/// never silently dropping a dirty line before the caller has a chance to
/// count it.
pub fn parse_rows<R: BufRead>(reader: R) -> impl Iterator<Item = Result<ProductRow, RowParseError>> {
    // `std::iter::once(todo!(...))` (rather than a bare `todo!(...)`) is
    // only here so this stub still type-checks against the `impl Iterator`
    // return type -- a bare `todo!()` has type `!`, which doesn't itself
    // implement `Iterator`. Calling this function still panics immediately.
    let _ = reader;
    std::iter::once(todo!(
        "reader.lines() yields io::Result<String> per line -- a read error here means something \
         is wrong with a file you just opened successfully, so `.expect(...)` on it is fine; map \
         the resulting String through parse_row. Replace this whole body with \
         reader.lines().map(...).map(...) -- don't collect into a Vec first and then turn that \
         back into an iterator, that defeats the point of the `impl Trait` streaming iterator"
    ))
}

/// Maps one Rust column type to the arrow builder that accumulates it and
/// the arrow `DataType` it should be written as. Implemented once per
/// column type so [`build_column`] can be written once, generically, and
/// reused for every column in [`ProductRow`] regardless of its Rust type.
pub trait ArrowColumn: Sized {
    type Builder: ArrayBuilder + Default;
    fn arrow_data_type() -> DataType;
    fn append(builder: &mut Self::Builder, value: &Self);
}

impl ArrowColumn for i64 {
    type Builder = Int64Builder;
    fn arrow_data_type() -> DataType {
        DataType::Int64
    }
    fn append(builder: &mut Self::Builder, value: &Self) {
        builder.append_value(*value);
    }
}

impl ArrowColumn for f64 {
    type Builder = Float64Builder;
    fn arrow_data_type() -> DataType {
        DataType::Float64
    }
    fn append(builder: &mut Self::Builder, value: &Self) {
        builder.append_value(*value);
    }
}

impl ArrowColumn for bool {
    type Builder = BooleanBuilder;
    fn arrow_data_type() -> DataType {
        DataType::Boolean
    }
    fn append(builder: &mut Self::Builder, value: &Self) {
        builder.append_value(*value);
    }
}

impl ArrowColumn for String {
    type Builder = StringBuilder;
    fn arrow_data_type() -> DataType {
        DataType::Utf8
    }
    fn append(builder: &mut Self::Builder, value: &Self) {
        builder.append_value(value.as_str());
    }
}

/// Builds one arrow column, generically over any `T: ArrowColumn`: a
/// `Field` named `name` typed with `T::arrow_data_type()`, and the
/// corresponding `ArrayRef` built by appending every value in `values`
/// through `T::Builder`. This is the one generic function every column of
/// [`ProductRow`] goes through, regardless of whether `T` is `i64`, `f64`,
/// `bool`, or `String`.
pub fn build_column<T: ArrowColumn>(name: &str, values: impl Iterator<Item = T>) -> (Field, ArrayRef) {
    todo!(
        "T::Builder::default() to get a fresh builder; loop over `values`, calling \
         T::append(&mut builder, &value) for each; builder.finish() gives you the ArrayRef \
         directly (ArrayBuilder::finish's return type); pair it with Field::new(name, \
         T::arrow_data_type(), false) -- false because this task's data has no nullable columns"
    )
}

/// Everything that can fail while writing the Parquet file, across the
/// row-parsing / arrow / parquet crate boundary.
#[derive(Debug)]
pub enum PipelineError {
    Io(std::io::Error),
    Arrow(ArrowError),
    Parquet(ParquetError),
}

impl fmt::Display for PipelineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PipelineError::Io(e) => write!(f, "I/O error: {e}"),
            PipelineError::Arrow(e) => write!(f, "arrow error: {e}"),
            PipelineError::Parquet(e) => write!(f, "parquet error: {e}"),
        }
    }
}

impl std::error::Error for PipelineError {}

impl From<std::io::Error> for PipelineError {
    fn from(err: std::io::Error) -> Self {
        PipelineError::Io(err)
    }
}

impl From<ArrowError> for PipelineError {
    fn from(err: ArrowError) -> Self {
        PipelineError::Arrow(err)
    }
}

impl From<ParquetError> for PipelineError {
    fn from(err: ParquetError) -> Self {
        PipelineError::Parquet(err)
    }
}

/// Row/dirty-row counts from one [`write_products_parquet`] run.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ConversionStats {
    pub total_rows: u64,
    pub valid_rows: u64,
    pub dirty_rows: u64,
}

/// Reads `csv_path` (skipping exactly its first line, the header), keeps
/// only the rows [`parse_row`] accepts, and writes them as one Parquet
/// file at `parquet_path`, Snappy-compressed, row groups capped at
/// `row_group_size` rows. The written schema, column order, and exact
/// arrow `DataType` per column are documented in README.md.
///
/// Returns counts of total/valid/dirty data rows seen -- a dirty row is
/// counted, never silently dropped uncounted.
pub fn write_products_parquet(
    csv_path: impl AsRef<Path>,
    parquet_path: impl AsRef<Path>,
    row_group_size: usize,
) -> Result<ConversionStats, PipelineError> {
    todo!(
        "open csv_path with a BufReader, read+discard exactly one line (the header) with \
         read_line into a scratch String, then hand the rest to parse_rows; fold the resulting \
         iterator into ConversionStats plus six Vec<_> column buffers (one per ProductRow \
         field), incrementing valid_rows/dirty_rows per Ok/Err; turn each Vec into a (Field, \
         ArrayRef) via build_column::<...>(name, vec.into_iter()); wrap the six Fields in an \
         arrow::datatypes::Schema behind an Arc, and RecordBatch::try_new(schema, columns)? ; \
         build a WriterProperties with .set_compression(parquet::basic::Compression::SNAPPY) \
         and .set_max_row_group_row_count(Some(row_group_size)); File::create(parquet_path)?, \
         then parquet::arrow::ArrowWriter::try_new(file, schema, Some(props))?, .write(&batch)?, \
         .close()?; return the ConversionStats"
    )
}
