//! Ungraded demo binary: wires ingest -> store -> export together end to
//! end against an in-process fixture server standing in for a real price
//! feed. `cargo test` never runs this; it exists so there's something to
//! run by hand once the pieces in `src/lib.rs` work.

use sandbox18_harness::async_fixture_server::{AsyncFixtureServer, RouteConfig};
use t08_capstone_price_watch::{export_parquet, ingest_batch, Store};

#[tokio::main]
async fn main() {
    let mut server = AsyncFixtureServer::builder()
        .route(
            "/price/widget-a",
            RouteConfig::new(200, r#"{"product_id":"widget-a","price":19.99,"scraped_at":1000}"#)
                .with_content_type("application/json"),
        )
        .route(
            "/price/widget-b",
            RouteConfig::new(200, r#"{"product_id":"widget-b","price":4.50,"scraped_at":1010}"#)
                .with_content_type("application/json"),
        )
        .route(
            "/price/widget-c",
            RouteConfig::new(200, r#"{"product_id":"widget-c","price":999.0,"scraped_at":1020}"#)
                .with_content_type("application/json"),
        )
        .start()
        .await;

    let dir = std::env::temp_dir().join("t08-capstone-price-watch-demo");
    std::fs::create_dir_all(&dir).expect("create demo store directory");
    let mut store = Store::open(&dir).expect("open bitcask store");

    let paths = vec![
        "/price/widget-a".to_string(),
        "/price/widget-b".to_string(),
        "/price/widget-c".to_string(),
    ];
    let report = ingest_batch(&server.base_url(), &paths, 4, &mut store).await;
    store.flush().expect("flush store after ingest");

    let failed = report.attempts.iter().filter(|a| a.result.is_err()).count();
    println!(
        "ingested {} paths ({} failed), wrote {} fresh records",
        report.attempts.len(),
        failed,
        report.written
    );

    let out_path = std::path::Path::new("prices.parquet");
    let rows = export_parquet(&store, out_path).expect("export parquet");
    println!("exported {rows} rows to {}", out_path.display());

    server.shutdown().await;
}
