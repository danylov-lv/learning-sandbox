//! CP1 — ingest + bitcask persistence.
//!
//! Two independent things are checked here:
//! 1. `ingest_batch` against a real `AsyncFixtureServer` serving a known,
//!    hand-authored set of price payloads ends up with a `Store` whose
//!    contents match that known set exactly (never the store's own second
//!    opinion of itself, never a hardcoded/constant map).
//! 2. `Store`'s crash recovery: a data file truncated mid-record (through a
//!    raw file handle, bypassing `Store` entirely) recovers exactly the
//!    records that were fully flushed before the cut, and nothing else.

mod common;

use common::{many_known_payloads, paths_of, start_server};

use t08_capstone_price_watch::{ingest_batch, put_latest_price, PriceRecord, Store};

const PRODUCT_COUNT: usize = 250;

#[tokio::test]
async fn ingest_persists_every_known_product_with_the_right_latest_price() {
    let payloads = many_known_payloads(PRODUCT_COUNT);
    let mut server = start_server(&payloads).await;
    let paths = paths_of(&payloads);

    let dir = tempfile::tempdir().expect("create temp dir for store");
    let mut store = Store::open(dir.path()).expect("open a fresh store");

    let report = ingest_batch(&server.base_url(), &paths, 16, &mut store).await;
    store.flush().expect("flush store after ingest");

    assert_eq!(
        report.attempts.len(),
        paths.len(),
        "ingest_batch must produce exactly one attempt per requested path, got {} for {} paths",
        report.attempts.len(),
        paths.len()
    );
    let failed: Vec<_> = report
        .attempts
        .iter()
        .filter(|a| a.result.is_err())
        .map(|a| format!("{}: {:?}", a.path, a.result))
        .collect();
    assert!(
        failed.is_empty(),
        "every route in this test returns 200 with a well-formed payload; these attempts \
         failed unexpectedly: {failed:?}"
    );
    assert_eq!(
        report.written, PRODUCT_COUNT,
        "every one of the {PRODUCT_COUNT} distinct products is new to this store, so every \
         successful fetch should have been written -- got {} written",
        report.written
    );

    common::assert_store_matches(&store, &payloads);

    server.shutdown().await;
}

fn record_len(product_id: &str) -> u64 {
    // header (12) + key bytes + fixed 16-byte value (price f64 + scraped_at u64)
    12 + product_id.len() as u64 + 16
}

#[test]
fn crash_mid_record_keeps_exactly_the_flushed_prefix() {
    let payloads = many_known_payloads(40);
    let (good, rest) = payloads.split_at(payloads.len() / 2);
    let torn = &rest[0];

    let dir = tempfile::tempdir().expect("create temp dir for store");
    let data_path = dir.path().join(t08_capstone_price_watch::DATA_FILE_NAME);

    let good_end;
    {
        let mut store = Store::open(dir.path()).expect("open store");
        for p in good {
            put_latest_price(
                &mut store,
                &PriceRecord {
                    product_id: p.product_id.clone(),
                    price: p.price,
                    scraped_at: p.scraped_at,
                },
            )
            .expect("put a good record");
        }
        store.flush().expect("flush good records so they are durable");
        good_end = std::fs::metadata(&data_path)
            .expect("stat data file after good records")
            .len();

        put_latest_price(
            &mut store,
            &PriceRecord {
                product_id: torn.product_id.clone(),
                price: torn.price,
                scraped_at: torn.scraped_at,
            },
        )
        .expect("put the record that will be torn");
        store
            .flush()
            .expect("flush the torn record so it is actually on disk to truncate");
    } // store dropped: releases the file handle before we truncate it directly

    let torn_len = record_len(&torn.product_id);
    let full_end = good_end + torn_len;
    // cut inside the 16-byte value half of the torn record
    let cut_at = good_end + 12 + torn.product_id.len() as u64 + 8;
    assert!(
        cut_at > good_end && cut_at < full_end,
        "test setup sanity: cut point must land strictly inside the torn record's bytes"
    );

    {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(&data_path)
            .expect("open data file directly, bypassing Store, to simulate a crash mid-write");
        file.set_len(cut_at)
            .expect("truncate data file to cut the trailing record in half");
    }

    let store = Store::open(dir.path()).expect(
        "reopening a store whose data file ends in a torn trailing record must not return Err",
    );

    common::assert_store_matches(&store, good);

    let snapshot = common::store_snapshot(&store);
    assert!(
        !snapshot.contains_key(&torn.product_id),
        "the torn record's product '{}' must be entirely absent after recovery -- not present \
         as a corrupted value, just gone, as if it had never been written",
        torn.product_id
    );
    assert_eq!(
        snapshot.len(),
        good.len(),
        "recovery must keep exactly the fully-flushed records and nothing from the torn tail"
    );
}
