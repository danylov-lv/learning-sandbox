//! CP3 — concurrency cap, crash recovery under ingest, and a filled-in
//! design memo. Also re-runs CP1/CP2-style checks so a regression
//! introduced while building CP3 doesn't slip through unnoticed.

mod common;

use std::collections::HashMap;
use std::time::Duration;

use arrow::array::{Float64Array, StringArray, UInt64Array};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use sandbox18_harness::async_fixture_server::{AsyncFixtureServer, RouteConfig};

use common::{many_known_payloads, paths_of, start_server};
use t08_capstone_price_watch::{export_parquet, ingest_batch, Store, DATA_FILE_NAME};

#[tokio::test]
async fn concurrency_cap_is_a_hard_ceiling_and_is_reached() {
    const CAP: usize = 3;
    const ROUTE_COUNT: usize = 9;

    let mut builder = AsyncFixtureServer::builder();
    let mut paths = Vec::new();
    for i in 0..ROUTE_COUNT {
        let path = format!("/price/slow-{i}");
        let json = format!(
            r#"{{"product_id":"slow-{i}","price":{},"scraped_at":{}}}"#,
            10.0 + i as f64,
            1_000 + i as u64
        );
        builder = builder.route(
            path.clone(),
            RouteConfig::new(200, json)
                .with_content_type("application/json")
                .with_delay(Duration::from_millis(150)),
        );
        paths.push(path);
    }

    let mut server = builder.start().await;
    let dir = tempfile::tempdir().expect("create temp dir for store");
    let mut store = Store::open(dir.path()).expect("open store");

    let report = ingest_batch(&server.base_url(), &paths, CAP, &mut store).await;

    assert_eq!(
        report.attempts.len(),
        ROUTE_COUNT,
        "every submitted path must produce exactly one attempt"
    );
    assert!(
        report.attempts.iter().all(|a| a.result.is_ok()),
        "every route here returns 200 with a valid payload after its delay; any failure means \
         a request was mishandled, not that the route is actually broken: {:?}",
        report.attempts.iter().filter(|a| a.result.is_err()).collect::<Vec<_>>()
    );

    let stats = server.stats().await;
    assert_eq!(
        stats.total_requests, ROUTE_COUNT as u64,
        "the fixture server's own counter should see exactly one request per path, got {}",
        stats.total_requests
    );
    assert!(
        stats.max_concurrency <= CAP as u64,
        "concurrency_cap={CAP} is a HARD ceiling: the server observed max_concurrency={}, which \
         must never exceed it -- an uncapped fan-out (spawning all requests at once with no \
         semaphore) would blow past this",
        stats.max_concurrency
    );
    assert!(
        stats.max_concurrency >= CAP as u64,
        "with {ROUTE_COUNT} delayed routes (3x the cap) and a 150ms delay giving ample overlap \
         window, genuinely capped-but-parallel ingest should drive concurrency all the way up to \
         the cap; observed max_concurrency={} suggests ingest under-parallelizes (a sequential \
         implementation would show max_concurrency=1)",
        stats.max_concurrency
    );

    server.shutdown().await;
}

#[tokio::test]
async fn crash_mid_ingest_then_resume_converges_to_full_expected_state() {
    let payloads = many_known_payloads(60);
    let mut server = start_server(&payloads).await;
    let all_paths = paths_of(&payloads);
    let (first_paths, _rest) = all_paths.split_at(all_paths.len() / 2);

    let dir = tempfile::tempdir().expect("create temp dir for store");
    let data_path = dir.path().join(DATA_FILE_NAME);

    {
        let mut store = Store::open(dir.path()).expect("open store");
        let report = ingest_batch(&server.base_url(), first_paths, 8, &mut store).await;
        assert!(
            report.attempts.iter().all(|a| a.result.is_ok()),
            "first half of ingest (before the simulated crash) should succeed cleanly"
        );
        store.flush().expect("flush the first half so it's on disk to truncate");
    } // store dropped here, releasing the file handle before we truncate it directly

    let len = std::fs::metadata(&data_path)
        .expect("stat data file after first-half ingest")
        .len();
    assert!(
        len > 1,
        "test setup sanity: data file should be non-trivial after ingesting {} records",
        first_paths.len()
    );
    {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(&data_path)
            .expect("open data file directly, bypassing Store, to simulate a crash mid-write");
        // Any record is at least 12 bytes, so removing exactly the last byte
        // always lands strictly inside the final record's bytes, never
        // exactly on a record boundary -- guaranteed to tear the tail.
        file.set_len(len - 1)
            .expect("truncate off the last byte to tear the final record");
    }

    let mut store = Store::open(dir.path())
        .expect("reopening a store after a simulated mid-ingest crash must not return Err");
    let resume_report = ingest_batch(&server.base_url(), &all_paths, 8, &mut store).await;
    store.flush().expect("flush after resuming ingest");

    assert!(
        resume_report.attempts.iter().all(|a| a.result.is_ok()),
        "resuming ingest over the FULL known set after recovery should succeed cleanly: {:?}",
        resume_report
            .attempts
            .iter()
            .filter(|a| a.result.is_err())
            .collect::<Vec<_>>()
    );

    common::assert_store_matches(&store, &payloads);

    server.shutdown().await;
}

const REQUIRED_HEADINGS: [&str; 6] = [
    "## Architecture and data flow",
    "## Concurrency cap and backpressure",
    "## Bitcask persistence and crash recovery",
    "## Freshness and idempotent convergence",
    "## Parquet export",
    "## Scaling to production",
];

const PLACEHOLDER_MARKER: &str = "[fill in";
const MIN_SECTION_CHARS: usize = 200;

const REQUIRED_KEYWORDS: [&[&str]; 4] = [
    &["semaphore", "concurrency", "cap"],
    &["keydir", "checksum", "truncat", "crash"],
    &["scraped_at", "idempotent", "converg"],
    &["parquet", "arrow", "recordbatch"],
];

fn extract_section<'a>(text: &'a str, heading: &str) -> Option<&'a str> {
    let start = text.find(heading)? + heading.len();
    let rest = &text[start..];
    let end = rest.find("\n## ").unwrap_or(rest.len());
    Some(rest[..end].trim())
}

#[test]
fn design_memo_is_filled_in() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/DESIGN.md");
    let text = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("could not read DESIGN.md at {path}: {e}"));

    let missing: Vec<&str> = REQUIRED_HEADINGS
        .iter()
        .filter(|h| !text.contains(*h))
        .copied()
        .collect();
    assert!(
        missing.is_empty(),
        "DESIGN.md is missing required section heading(s): {missing:?}"
    );

    for heading in REQUIRED_HEADINGS {
        let content = extract_section(&text, heading)
            .unwrap_or_else(|| panic!("could not extract content under '{heading}'"));
        assert!(
            !content.contains(PLACEHOLDER_MARKER),
            "section '{heading}' still contains the shipped '[fill in' placeholder -- replace \
             it with your own analysis grounded in what you actually built"
        );
        let char_count = content.chars().filter(|c| !c.is_whitespace()).count();
        assert!(
            char_count >= MIN_SECTION_CHARS,
            "section '{heading}' has only {char_count} non-whitespace characters, expected at \
             least {MIN_SECTION_CHARS} -- write a real analysis, not a placeholder-sized stub"
        );
    }

    let lower = text.to_lowercase();
    let missing_keywords: Vec<&&str> = REQUIRED_KEYWORDS
        .iter()
        .filter_map(|group| {
            let hit = group.iter().any(|kw| lower.contains(kw));
            if hit { None } else { group.first() }
        })
        .collect();
    assert!(
        missing_keywords.is_empty(),
        "DESIGN.md doesn't mention required concept(s) near: {missing_keywords:?} -- the memo \
         must be grounded in this capstone's own vocabulary, not generic prose about bitcask or \
         Parquet in the abstract"
    );
}

#[tokio::test]
async fn rerun_cp1_and_cp2_style_checks() {
    let payloads = many_known_payloads(30);
    let mut server = start_server(&payloads).await;
    let paths = paths_of(&payloads);

    let dir = tempfile::tempdir().expect("create temp dir for store");
    let mut store = Store::open(dir.path()).expect("open store");
    let report = ingest_batch(&server.base_url(), &paths, 6, &mut store).await;
    store.flush().expect("flush after ingest");

    assert!(
        report.attempts.iter().all(|a| a.result.is_ok()),
        "CP1-style re-check: every known route should ingest successfully"
    );
    common::assert_store_matches(&store, &payloads);

    let out_path = dir.path().join("rerun.parquet");
    let rows = export_parquet(&store, &out_path).expect("export parquet");
    assert_eq!(
        rows,
        payloads.len(),
        "CP2-style re-check: exported row count should match the distinct product count"
    );

    let file = std::fs::File::open(&out_path).expect("open re-exported parquet file");
    let reader = ParquetRecordBatchReaderBuilder::try_new(file)
        .expect("build parquet reader")
        .build()
        .expect("construct record batch reader");

    let mut seen: HashMap<String, (f64, u64)> = HashMap::new();
    for batch in reader {
        let batch = batch.expect("read record batch");
        let ids = batch.column(0).as_any().downcast_ref::<StringArray>().unwrap();
        let prices = batch.column(1).as_any().downcast_ref::<Float64Array>().unwrap();
        let ats = batch.column(2).as_any().downcast_ref::<UInt64Array>().unwrap();
        for row in 0..batch.num_rows() {
            seen.insert(ids.value(row).to_string(), (prices.value(row), ats.value(row)));
        }
    }

    for p in &payloads {
        let (price, scraped_at) = seen.get(&p.product_id).unwrap_or_else(|| {
            panic!(
                "CP2-style re-check: product '{}' missing from re-exported parquet file",
                p.product_id
            )
        });
        assert!(
            (price - p.price).abs() < 1e-9,
            "CP2-style re-check: product '{}' price mismatch in rerun export",
            p.product_id
        );
        assert_eq!(
            *scraped_at, p.scraped_at,
            "CP2-style re-check: product '{}' scraped_at mismatch in rerun export",
            p.product_id
        );
    }

    server.shutdown().await;
}
