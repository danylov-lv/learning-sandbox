//! CP2 — Parquet export + end-to-end freshness.
//!
//! Ingests a mix of products where a handful have *three* observations at
//! different `scraped_at` values (the "real" one, a clearly fresher one,
//! and a clearly staler one that is deliberately delayed so it reliably
//! finishes ingesting LAST). Only comparing `scraped_at` numerically -- not
//! arrival order, not which route was listed first in `paths` -- picks the
//! right winner. Exports to Parquet, reads the file back independently via
//! `parquet::arrow::arrow_reader`, and checks row count, per-product price,
//! and that every exported row really is the freshest observation seen for
//! its product.

mod common;

use std::collections::HashMap;
use std::time::Duration;

use arrow::array::{Float64Array, StringArray, UInt64Array};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use sandbox18_harness::async_fixture_server::{AsyncFixtureServer, RouteConfig};

use common::{many_known_payloads, payload_json};
use t08_capstone_price_watch::{export_parquet, ingest_batch, Store};

const PRODUCT_COUNT: usize = 40;
const DUPLICATED_COUNT: usize = 5;

#[tokio::test]
async fn export_reflects_freshest_observation_per_product_and_round_trips() {
    let base_payloads = many_known_payloads(PRODUCT_COUNT);

    let mut builder = AsyncFixtureServer::builder();
    for p in &base_payloads {
        builder = builder.route(
            p.path.clone(),
            RouteConfig::new(200, payload_json(p)).with_content_type("application/json"),
        );
    }

    // product_id -> (expected freshest price, expected freshest scraped_at)
    let mut expected: HashMap<String, (f64, u64)> = base_payloads
        .iter()
        .map(|p| (p.product_id.clone(), (p.price, p.scraped_at)))
        .collect();

    let mut paths = common::paths_of(&base_payloads);

    for (i, p) in base_payloads.iter().take(DUPLICATED_COUNT).enumerate() {
        let fresh_path = format!("/price/{}/fresh-{i}", p.product_id);
        let fresh_scraped_at = p.scraped_at + 10_000;
        let fresh_price = 5000.0 + i as f64;
        let fresh_json = format!(
            r#"{{"product_id":"{}","price":{},"scraped_at":{}}}"#,
            p.product_id, fresh_price, fresh_scraped_at
        );
        builder = builder.route(
            fresh_path.clone(),
            RouteConfig::new(200, fresh_json).with_content_type("application/json"),
        );
        paths.push(fresh_path);

        let stale_path = format!("/price/{}/stale-{i}", p.product_id);
        let stale_scraped_at = p.scraped_at.saturating_sub(500);
        let stale_price = 1.0 + i as f64;
        let stale_json = format!(
            r#"{{"product_id":"{}","price":{},"scraped_at":{}}}"#,
            p.product_id, stale_price, stale_scraped_at
        );
        // Delayed so this response reliably finishes LAST among this
        // product's three observations. A "last completed write wins"
        // implementation (instead of comparing scraped_at) would end up
        // keeping this clearly-stale value -- this is the anti-cheat.
        builder = builder.route(
            stale_path.clone(),
            RouteConfig::new(200, stale_json)
                .with_content_type("application/json")
                .with_delay(Duration::from_millis(60)),
        );
        paths.push(stale_path);

        expected.insert(p.product_id.clone(), (fresh_price, fresh_scraped_at));
    }

    let mut server = builder.start().await;

    let dir = tempfile::tempdir().expect("create temp dir for store");
    let mut store = Store::open(dir.path()).expect("open store");

    let report = ingest_batch(&server.base_url(), &paths, 12, &mut store).await;
    store.flush().expect("flush store after ingest");

    assert_eq!(
        report.attempts.len(),
        paths.len(),
        "ingest_batch must produce exactly one attempt per requested path"
    );
    let failed: Vec<_> = report.attempts.iter().filter(|a| a.result.is_err()).collect();
    assert!(
        failed.is_empty(),
        "every configured route returns 200 with a valid payload; unexpected failures: {failed:?}"
    );

    // Sanity on the store itself before even touching Parquet.
    let snapshot = common::store_snapshot(&store);
    assert_eq!(
        snapshot.len(),
        expected.len(),
        "store must have exactly one record per distinct product ({}), not per path ({}) -- \
         multiple observations of the same product must collapse to one record",
        expected.len(),
        paths.len()
    );
    for (product_id, (price, scraped_at)) in &expected {
        let (got_price, got_scraped_at) = snapshot
            .get(product_id)
            .unwrap_or_else(|| panic!("product '{product_id}' missing from store after ingest"));
        assert!(
            (got_price - price).abs() < 1e-9,
            "product '{product_id}': store price {got_price} != expected freshest price {price} \
             -- a stale, delayed-but-later-arriving observation was likely allowed to win"
        );
        assert_eq!(
            got_scraped_at, scraped_at,
            "product '{product_id}': store scraped_at {got_scraped_at} != expected freshest \
             {scraped_at}"
        );
    }

    let out_path = dir.path().join("export.parquet");
    let rows_reported = export_parquet(&store, &out_path).expect("export parquet");
    assert_eq!(
        rows_reported, expected.len(),
        "export_parquet's reported row count should match the number of distinct products"
    );

    // Read the exported file back INDEPENDENTLY via arrow/parquet's own
    // reader -- never through any of the learner's own store-reading code
    // -- and compare against this test's hardcoded `expected` map.
    let file = std::fs::File::open(&out_path).expect("open exported parquet file");
    let reader = ParquetRecordBatchReaderBuilder::try_new(file)
        .expect("build parquet reader")
        .build()
        .expect("construct record batch reader");

    let mut seen: HashMap<String, (f64, u64)> = HashMap::new();
    for batch in reader {
        let batch = batch.expect("read a record batch from the exported file");
        let ids = batch
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .expect("column 0 should be product_id: Utf8");
        let prices = batch
            .column(1)
            .as_any()
            .downcast_ref::<Float64Array>()
            .expect("column 1 should be price: Float64");
        let ats = batch
            .column(2)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .expect("column 2 should be scraped_at: UInt64");
        for row in 0..batch.num_rows() {
            seen.insert(ids.value(row).to_string(), (prices.value(row), ats.value(row)));
        }
    }

    assert_eq!(
        seen.len(),
        expected.len(),
        "exported parquet file should have exactly one row per distinct product, got {} rows \
         for {} products",
        seen.len(),
        expected.len()
    );
    for (product_id, (price, scraped_at)) in &expected {
        let (got_price, got_scraped_at) = seen
            .get(product_id)
            .unwrap_or_else(|| panic!("product '{product_id}' missing from exported parquet file"));
        assert!(
            (got_price - price).abs() < 1e-9,
            "parquet row for '{product_id}': price {got_price} != expected freshest price {price}"
        );
        assert_eq!(
            *got_scraped_at, *scraped_at,
            "parquet row for '{product_id}': scraped_at {got_scraped_at} != expected freshest \
             {scraped_at} -- freshness property violated: this row is not the latest-seen \
             observation for its product"
        );
    }

    server.shutdown().await;
}
