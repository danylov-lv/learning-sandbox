//! Loads the ground-truth answer key written by `sandbox18-datagen`, and
//! locates the module root robustly regardless of which task crate calls it.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

/// Finds `18-rust-track/` by walking up from `CARGO_MANIFEST_DIR` (a runtime
/// env var Cargo sets for every crate it builds and runs, not the
/// compile-time `env!` macro — this must work no matter which task crate's
/// binary or test harness is executing) until a `data/ground-truth.json`
/// marker is found. Falls back to the manifest dir's parent, which is
/// correct for every task crate today (they all live one level below the
/// module root).
pub fn module_root() -> PathBuf {
    let manifest_dir = std::env::var("CARGO_MANIFEST_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| std::env::current_dir().expect("no current directory"));

    let mut dir: &Path = manifest_dir.as_path();
    loop {
        if dir.join("data").join("ground-truth.json").is_file() {
            return dir.to_path_buf();
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }

    manifest_dir
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or(manifest_dir)
}

/// Path to a named file under the module's `data/` directory.
pub fn data_path(name: &str) -> PathBuf {
    module_root().join("data").join(name)
}

/// Loads and deserializes `data/ground-truth.json`. Panics with a clear
/// message on a missing or malformed file — run `cargo run -p
/// sandbox18-datagen` first if this fails.
pub fn load() -> GroundTruth {
    let path = data_path("ground-truth.json");
    let bytes = std::fs::read(&path).unwrap_or_else(|e| {
        panic!(
            "failed to read ground truth at {}: {e}\n\
             hint: run `cargo run -p sandbox18-datagen` from the module root first",
            path.display()
        )
    });
    serde_json::from_slice(&bytes)
        .unwrap_or_else(|e| panic!("failed to parse ground truth json at {}: {e}", path.display()))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroundTruth {
    pub seed: u64,
    pub scale: f64,
    pub log: LogGroundTruth,
    pub csv: CsvGroundTruth,
}

/// Aggregates independently computed over `data/access.log`, consumed by
/// tasks 01 (log parser) and 06 (TUI dashboard).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogGroundTruth {
    pub total_lines: u64,
    pub well_formed_lines: u64,
    pub malformed_lines: u64,
    /// Keyed by "2xx"/"3xx"/"4xx"/"5xx". A `BTreeMap` (not `HashMap`) so JSON
    /// key order — and therefore the serialized bytes — is stable across
    /// process runs; `HashMap`'s per-process random hasher would otherwise
    /// break byte-identical regeneration.
    pub status_class_counts: BTreeMap<String, u64>,
    pub method_counts: BTreeMap<String, u64>,
    /// Full per-path request histogram over well-formed lines.
    pub path_counts: BTreeMap<String, u64>,
    /// Top 10 paths by request count, descending, ties broken by path name
    /// ascending — a stable order so tests can assert on it directly.
    pub top_paths: Vec<PathCount>,
    pub unique_ips: u64,
    pub error_rate_5xx: f64,
    pub response_time_ms: ResponseTimeStats,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathCount {
    pub path: String,
    pub count: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResponseTimeStats {
    pub mean_ms: f64,
    pub p50_ms: f64,
    pub p95_ms: f64,
    pub p99_ms: f64,
    pub max_ms: f64,
}

/// Aggregates independently computed over `data/products.csv`, consumed by
/// task 03 (CSV to Parquet).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CsvGroundTruth {
    pub total_rows: u64,
    pub valid_rows: u64,
    pub dirty_rows: u64,
    pub in_stock_count: u64,
    pub out_of_stock_count: u64,
    /// Keyed by category name, valid rows only.
    pub category_counts: BTreeMap<String, u64>,
    pub category_price_stats: BTreeMap<String, PriceStats>,
    pub overall_price_stats: PriceStats,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceStats {
    pub count: u64,
    pub min: f64,
    pub max: f64,
    pub mean: f64,
    pub sum: f64,
}
