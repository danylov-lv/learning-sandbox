//! Thin CLI wrapper. Not graded -- `tests/` is the validator. Useful once
//! the library is implemented, to point it at anything of your own choosing
//! (there is no real network access anywhere else in this module's tests).
//!
//! Usage: `cargo run -p t07-async-fetch-pipeline -- <url> [url...]`

use std::sync::Arc;
use std::time::Duration;

use t07_async_fetch_pipeline::{PipelineConfig, ShutdownSignal, TcpFetcher, spawn_pipeline};

#[tokio::main]
async fn main() {
    let urls: Vec<String> = std::env::args().skip(1).collect();
    let urls = if urls.is_empty() {
        vec!["http://127.0.0.1:1/placeholder".to_string()]
    } else {
        urls
    };

    let fetcher = Arc::new(TcpFetcher::new(
        Duration::from_secs(2),
        2,
        Duration::from_millis(100),
        2,
    ));
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: 8,
        channel_capacity: 16,
    };

    let mut handle = spawn_pipeline(fetcher, urls, config, shutdown_rx);
    while let Some(report) = handle.receiver.recv().await {
        println!("{} -> {:?}", report.url, report.outcome);
    }
    let outcome = handle.join().await;
    println!(
        "done: {} task(s) spawned, cancelled={}",
        outcome.tasks_spawned, outcome.cancelled
    );
}
