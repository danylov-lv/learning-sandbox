//! Grades the concurrency cap STRUCTURALLY, against the fixture server's own
//! independently-tracked `stats().max_concurrency` -- never against
//! wall-clock elapsed time. Uses the real `HttpChecker` + `FixtureServer` so
//! actual sockets are actually in flight, not a simulation of concurrency.

use std::time::Duration;

use sandbox18_harness::fixture_server::{FixtureServer, RouteConfig};
use t04_url_health_checker::{check_urls_concurrently, HttpChecker};

#[test]
fn pool_never_exceeds_the_cap_but_does_reach_it() {
    const CAP: usize = 4;
    const URL_COUNT: usize = 12;

    let server = FixtureServer::builder()
        .route(
            "/slow",
            RouteConfig::new(200, "ok").with_delay(Duration::from_millis(150)),
        )
        .start();
    let urls: Vec<String> = (0..URL_COUNT)
        .map(|_| format!("{}/slow", server.base_url()))
        .collect();

    let checker = HttpChecker::new(Duration::from_secs(2), Duration::from_secs(2), 0);
    let reports = check_urls_concurrently(&checker, &urls, CAP);

    assert_eq!(
        reports.len(),
        URL_COUNT,
        "every submitted URL must produce exactly one report -- a pool that drops or \
         duplicates work would fail this before concurrency even matters"
    );
    assert!(
        reports.iter().all(|r| r.outcome.is_healthy()),
        "the /slow route always eventually answers 200 with plenty of timeout headroom; any \
         report that isn't Healthy means a request was mishandled by the pool or the client, \
         not that the route is actually unhealthy: {reports:?}"
    );

    let stats = server.stats();
    assert_eq!(
        stats.total_requests,
        URL_COUNT as u64,
        "the fixture server's own request counter should see exactly one request per URL, got {}",
        stats.total_requests
    );
    assert!(
        stats.max_concurrency <= CAP as u64,
        "worker_count={CAP} is a HARD cap: the server observed max_concurrency={}, which must \
         never exceed it -- a pool spawning one thread per URL instead of a fixed pool of {CAP} \
         would blow past this",
        stats.max_concurrency
    );
    assert!(
        stats.max_concurrency >= CAP as u64,
        "with {URL_COUNT} delayed requests (3x the cap) and a 150ms delay giving ample overlap \
         window, a genuinely parallel pool should drive concurrency all the way up to the cap; \
         observed max_concurrency={} suggests the pool under-parallelizes (a sequential \
         implementation would show max_concurrency=1)",
        stats.max_concurrency
    );
}

#[test]
fn a_single_worker_never_lets_two_requests_overlap() {
    let server = FixtureServer::builder()
        .route(
            "/slow",
            RouteConfig::new(200, "ok").with_delay(Duration::from_millis(80)),
        )
        .start();
    let urls: Vec<String> = (0..5)
        .map(|_| format!("{}/slow", server.base_url()))
        .collect();

    let checker = HttpChecker::new(Duration::from_secs(2), Duration::from_secs(2), 0);
    let reports = check_urls_concurrently(&checker, &urls, 1);

    assert_eq!(reports.len(), 5, "all 5 URLs must still be checked with only 1 worker");
    let stats = server.stats();
    assert_eq!(
        stats.max_concurrency, 1,
        "worker_count=1 must fully serialize requests; observed max_concurrency={} means more \
         than one request was in flight at once despite a cap of 1",
        stats.max_concurrency
    );
}
