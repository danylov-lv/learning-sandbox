//! Exercises the real `TcpFetcher` against the given
//! `sandbox18_harness::async_fixture_server`: one outcome variant per
//! scenario the README's HTTP subset, retry/backoff contract, and timeout
//! contract describe. No fake standing in here -- these tests actually open
//! sockets. Retries are graded by request COUNT against the server's own
//! `stats()`, never by elapsed wall-clock time.

mod common;

use std::time::Duration;

use sandbox18_harness::async_fixture_server::{AsyncFixtureServer, RouteConfig};
use t07_async_fetch_pipeline::{FetchOutcome, Fetcher, TcpFetcher};

fn fetcher(max_retries: u32) -> TcpFetcher {
    TcpFetcher::new(
        Duration::from_millis(500),
        max_retries,
        Duration::from_millis(10),
        2,
    )
}

#[tokio::test]
async fn ok_route_is_healthy_with_one_attempt() {
    let server = AsyncFixtureServer::builder()
        .route("/ok", RouteConfig::new(200, "hello"))
        .start()
        .await;
    let url = format!("{}/ok", server.base_url());

    let outcome = fetcher(0).fetch(&url).await;

    match outcome {
        FetchOutcome::Healthy { status, attempts } => {
            assert_eq!(status, 200, "expected status 200 for a plain /ok route, got {status}");
            assert_eq!(
                attempts, 1,
                "a first-try success must report exactly 1 attempt, got {attempts}"
            );
        }
        other => panic!("expected FetchOutcome::Healthy for a 200 route, got {other:?}"),
    }
}

#[tokio::test]
async fn not_found_and_server_error_are_unhealthy_and_never_retried() {
    let mut server = AsyncFixtureServer::builder()
        .route("/notfound", RouteConfig::new(404, "nope"))
        .route("/err", RouteConfig::new(500, "boom"))
        .start()
        .await;
    // Nonzero retry budget on purpose: proves a real HTTP status is never
    // retried even when the fetcher would be willing to.
    let f = fetcher(3);

    let outcome_404 = f.fetch(&format!("{}/notfound", server.base_url())).await;
    let outcome_500 = f.fetch(&format!("{}/err", server.base_url())).await;

    match outcome_404 {
        FetchOutcome::Unhealthy { status, attempts } => {
            assert_eq!(status, 404, "expected 404 preserved in the outcome, got {status}");
            assert_eq!(attempts, 1, "a non-2xx response must never be retried, got {attempts}");
        }
        other => panic!("expected Unhealthy for a 404 route, got {other:?}"),
    }
    match outcome_500 {
        FetchOutcome::Unhealthy { status, attempts } => {
            assert_eq!(status, 500, "expected 500 preserved in the outcome, got {status}");
            assert_eq!(attempts, 1, "a non-2xx response must never be retried, got {attempts}");
        }
        other => panic!("expected Unhealthy for a 500 route, got {other:?}"),
    }
    // Two different non-2xx statuses must map to two different reported
    // statuses -- a fetcher that hardcodes one status value would pass one
    // of the two match arms above and fail the other.

    let stats = server.stats().await;
    assert_eq!(
        stats.requests_by_path.get("/notfound"),
        Some(&1),
        "a 404 must never be retried -- the server should see exactly 1 request to /notfound \
         despite a retry budget of 3, got {:?}",
        stats.requests_by_path.get("/notfound")
    );
    assert_eq!(
        stats.requests_by_path.get("/err"),
        Some(&1),
        "a 500 must never be retried -- the server should see exactly 1 request to /err \
         despite a retry budget of 3, got {:?}",
        stats.requests_by_path.get("/err")
    );

    server.shutdown().await;
}

#[tokio::test]
async fn flaky_route_succeeds_after_retries_within_budget() {
    let mut server = AsyncFixtureServer::builder()
        .route("/flaky", RouteConfig::new(200, "eventually ok").fail_first(2))
        .start()
        .await;
    let url = format!("{}/flaky", server.base_url());

    // Budget is 1 + max_retries = 3 attempts; fail_first(2) drops exactly
    // the first 2, so the 3rd must land inside the budget and succeed.
    let outcome = fetcher(2).fetch(&url).await;

    match outcome {
        FetchOutcome::Healthy { status, attempts } => {
            assert_eq!(status, 200, "the flaky route's real status is 200 once it stops failing");
            assert_eq!(
                attempts, 3,
                "fail_first(2) drops the first 2 attempts; the 3rd must succeed, so attempts \
                 should be 3, got {attempts}"
            );
        }
        other => panic!("expected Healthy after retrying past a fail_first(2) route, got {other:?}"),
    }

    let stats = server.stats().await;
    assert_eq!(
        stats.requests_by_path.get("/flaky"),
        Some(&3),
        "retry is graded by request COUNT, not elapsed time: the server should have seen \
         exactly 3 requests to /flaky (2 dropped connections + 1 that succeeded), got {:?}",
        stats.requests_by_path.get("/flaky")
    );

    server.shutdown().await;
}

#[tokio::test]
async fn flaky_route_exhausts_retry_budget_and_reports_connection_failed() {
    let mut server = AsyncFixtureServer::builder()
        .route("/very-flaky", RouteConfig::new(200, "ok").fail_first(5))
        .start()
        .await;
    let url = format!("{}/very-flaky", server.base_url());

    // Budget is 1 + max_retries = 3 attempts, but fail_first(5) drops every
    // one of them -- the budget must run out before the route ever
    // succeeds.
    let outcome = fetcher(2).fetch(&url).await;

    match outcome {
        FetchOutcome::ConnectionFailed { attempts } => assert_eq!(
            attempts, 3,
            "max_retries=2 means a budget of 1+2=3 attempts before giving up permanently, got \
             {attempts}"
        ),
        other => panic!(
            "expected ConnectionFailed once the retry budget is exhausted against a route still \
             failing every attempt, got {other:?}"
        ),
    }

    let stats = server.stats().await;
    assert_eq!(
        stats.requests_by_path.get("/very-flaky"),
        Some(&3),
        "the fetcher must stop once its own attempt budget (3) is exhausted, not keep hammering \
         the route -- server saw {:?} requests",
        stats.requests_by_path.get("/very-flaky")
    );

    server.shutdown().await;
}

#[tokio::test]
async fn connection_refused_reports_failure_after_exhausting_retry_budget() {
    let port = common::closed_port();
    let url = format!("http://127.0.0.1:{port}/anything");

    // A generous request_timeout here on purpose: refusing a connection to
    // a closed local port is a connection-level failure, not a slow
    // response, but the OS still needs some time to hand back the refusal.
    // A short request_timeout would risk misclassifying this as Timeout
    // instead of ConnectionFailed on a loaded machine -- the fetch itself
    // still returns almost immediately once the OS actually refuses.
    let f = TcpFetcher::new(Duration::from_secs(5), 2, Duration::from_millis(10), 2);
    let outcome = f.fetch(&url).await;

    match outcome {
        FetchOutcome::ConnectionFailed { attempts } => assert_eq!(
            attempts, 3,
            "max_retries=2 means a budget of 1+2=3 attempts before giving up permanently \
             against a port nobody is listening on, got {attempts}"
        ),
        other => panic!(
            "expected ConnectionFailed against a closed port with no listener, got {other:?}"
        ),
    }
}

#[tokio::test]
async fn slow_route_past_request_timeout_reports_timeout_and_is_not_retried() {
    let mut server = AsyncFixtureServer::builder()
        .route(
            "/slow",
            RouteConfig::new(200, "too slow").with_delay(Duration::from_millis(300)),
        )
        .start()
        .await;
    let url = format!("{}/slow", server.base_url());

    // request_timeout (30ms) is far shorter than the route's delay (300ms),
    // and max_retries is nonzero to prove a timeout is NOT retried into a
    // different outcome.
    let f = TcpFetcher::new(Duration::from_millis(30), 3, Duration::from_millis(5), 2);
    let outcome = f.fetch(&url).await;

    assert_eq!(
        outcome,
        FetchOutcome::Timeout,
        "a route delayed well past request_timeout must report Timeout and must not be retried \
         into some other outcome, got {outcome:?}"
    );
    assert_eq!(
        outcome.attempts(),
        1,
        "Timeout is always exactly 1 attempt by definition, got {}",
        outcome.attempts()
    );

    let stats = server.stats().await;
    assert_eq!(
        stats.requests_by_path.get("/slow"),
        Some(&1),
        "a timeout must never be retried -- the server should see exactly 1 request to /slow \
         despite a nonzero max_retries budget, got {:?}",
        stats.requests_by_path.get("/slow")
    );

    server.shutdown().await;
}
