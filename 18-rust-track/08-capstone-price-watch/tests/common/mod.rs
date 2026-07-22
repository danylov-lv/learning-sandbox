//! Shared fixtures for cp1/cp2/cp3: a known, independently-authored set of
//! price payloads (never derived from the learner's own code) and helpers
//! to serve them off an `AsyncFixtureServer` and check a `Store`'s contents
//! against them.

use std::collections::HashMap;

use sandbox18_harness::async_fixture_server::{AsyncFixtureServer, RouteConfig};

use t08_capstone_price_watch::{all_latest_prices, Store};

/// One route's worth of known, hand-authored expectation.
#[derive(Debug, Clone)]
pub struct KnownPayload {
    pub path: String,
    pub product_id: String,
    pub price: f64,
    pub scraped_at: u64,
}

pub fn payload_json(p: &KnownPayload) -> String {
    format!(
        r#"{{"product_id":"{}","price":{},"scraped_at":{}}}"#,
        p.product_id, p.price, p.scraped_at
    )
}

/// A large set of distinct products: distinct prices, distinct
/// `scraped_at` values, and enough records that writing them all before a
/// single flush would overrun any fixed-size (non-growing) buffer.
pub fn many_known_payloads(count: usize) -> Vec<KnownPayload> {
    (0..count)
        .map(|i| {
            let product_id = format!("product-{i:04}");
            let path = format!("/price/{product_id}");
            KnownPayload {
                price: 1.0 + (i as f64) * 1.37,
                scraped_at: 1_000 + (i as u64) * 7,
                path,
                product_id,
            }
        })
        .collect()
}

pub fn paths_of(payloads: &[KnownPayload]) -> Vec<String> {
    payloads.iter().map(|p| p.path.clone()).collect()
}

/// Starts an `AsyncFixtureServer` with one route per payload, each
/// returning that payload's exact JSON body.
pub async fn start_server(payloads: &[KnownPayload]) -> AsyncFixtureServer {
    let mut builder = AsyncFixtureServer::builder();
    for p in payloads {
        builder = builder.route(
            p.path.clone(),
            RouteConfig::new(200, payload_json(p)).with_content_type("application/json"),
        );
    }
    builder.start().await
}

/// Reads back every product currently in `store` as a `product_id -> (price,
/// scraped_at)` map, for easy comparison against a known expectation map.
pub fn store_snapshot(store: &Store) -> HashMap<String, (f64, u64)> {
    all_latest_prices(store)
        .expect("read back store contents")
        .into_iter()
        .map(|r| (r.product_id, (r.price, r.scraped_at)))
        .collect()
}

/// Asserts `store` holds exactly one record per payload in `expected`, with
/// prices and `scraped_at` matching exactly.
pub fn assert_store_matches(store: &Store, expected: &[KnownPayload]) {
    let mut got = store_snapshot(store);

    assert_eq!(
        got.len(),
        expected.len(),
        "store should hold exactly one record per known product ({}), got {} -- a stub \
         returning an empty or constant map would fail here immediately",
        expected.len(),
        got.len()
    );

    for p in expected {
        let (price, scraped_at) = got.remove(&p.product_id).unwrap_or_else(|| {
            panic!(
                "product '{}' is missing from the store entirely after ingest",
                p.product_id
            )
        });
        assert!(
            (price - p.price).abs() < 1e-9,
            "product '{}': expected price {}, got {price}",
            p.product_id,
            p.price
        );
        assert_eq!(
            scraped_at, p.scraped_at,
            "product '{}': expected scraped_at {}, got {scraped_at}",
            p.product_id, p.scraped_at
        );
    }
}
