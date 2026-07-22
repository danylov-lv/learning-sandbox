//! Exercises the real `HttpChecker` against the given fixture server: one
//! outcome variant per scenario the README's HTTP subset and retry contract
//! describe. No fake standing in here -- these tests actually open sockets
//! against `sandbox18_harness::fixture_server`.

mod common;

use std::time::Duration;

use sandbox18_harness::fixture_server::{FixtureServer, RouteConfig};
use t04_url_health_checker::{CheckOutcome, Checker, HttpChecker};

fn checker(max_retries: u32) -> HttpChecker {
    HttpChecker::new(
        Duration::from_millis(500),
        Duration::from_millis(300),
        max_retries,
    )
}

#[test]
fn ok_route_is_healthy_with_one_attempt() {
    let server = FixtureServer::builder()
        .route("/ok", RouteConfig::new(200, "hello"))
        .start();
    let url = format!("{}/ok", server.base_url());

    let outcome = checker(0).check(&url);

    match outcome {
        CheckOutcome::Healthy { status, attempts } => {
            assert_eq!(status, 200, "expected status 200 for a plain /ok route, got {status}");
            assert_eq!(
                attempts, 1,
                "a first-try success must report exactly 1 attempt, got {attempts}"
            );
        }
        other => panic!("expected CheckOutcome::Healthy for a 200 route, got {other:?}"),
    }
}

#[test]
fn not_found_and_server_error_both_classify_unhealthy_with_their_own_status() {
    let server = FixtureServer::builder()
        .route("/missing", RouteConfig::new(404, "nope"))
        .route("/broken", RouteConfig::new(500, "boom"))
        .start();
    let c = checker(0);

    let outcome_404 = c.check(&format!("{}/missing", server.base_url()));
    let outcome_500 = c.check(&format!("{}/broken", server.base_url()));

    match outcome_404 {
        CheckOutcome::Unhealthy { status, .. } => {
            assert_eq!(status, 404, "expected 404 preserved in the outcome, got {status}")
        }
        other => panic!("expected Unhealthy for a 404 route, got {other:?}"),
    }
    match outcome_500 {
        CheckOutcome::Unhealthy { status, .. } => {
            assert_eq!(status, 500, "expected 500 preserved in the outcome, got {status}")
        }
        other => panic!("expected Unhealthy for a 500 route, got {other:?}"),
    }
    // Two different non-2xx statuses must map to two different reported
    // statuses -- a checker that hardcodes one status value would pass one
    // of the two match arms above and fail the other.
}

#[test]
fn flaky_route_succeeds_after_retries_within_budget() {
    let server = FixtureServer::builder()
        .route("/flaky", RouteConfig::new(200, "eventually ok").fail_first(2))
        .start();
    let url = format!("{}/flaky", server.base_url());

    // Budget is 1 + max_retries = 3 attempts; fail_first(2) drops exactly
    // the first 2, so the 3rd must land inside the budget and succeed.
    let outcome = checker(2).check(&url);

    match outcome {
        CheckOutcome::Healthy { status, attempts } => {
            assert_eq!(status, 200, "the flaky route's real status is 200 once it stops failing");
            assert_eq!(
                attempts, 3,
                "fail_first(2) drops the first 2 attempts; the 3rd must succeed, so attempts \
                 should be 3, got {attempts}"
            );
        }
        other => panic!(
            "expected Healthy after retrying past a fail_first(2) route, got {other:?}"
        ),
    }
}

#[test]
fn connection_refused_reports_failure_after_exhausting_retry_budget() {
    let port = common::closed_port();
    let url = format!("http://127.0.0.1:{port}/anything");

    let outcome = checker(2).check(&url);

    match outcome {
        CheckOutcome::ConnectionFailed { attempts } => assert_eq!(
            attempts, 3,
            "max_retries=2 means a budget of 1+2=3 attempts before giving up permanently, got {attempts}"
        ),
        other => panic!(
            "expected ConnectionFailed against a closed port with no listener, got {other:?}"
        ),
    }
}

#[test]
fn slow_route_past_read_timeout_reports_timeout_not_something_else() {
    let server = FixtureServer::builder()
        .route(
            "/slow",
            RouteConfig::new(200, "too slow").with_delay(Duration::from_millis(400)),
        )
        .start();
    let url = format!("{}/slow", server.base_url());

    // read_timeout (80ms) is far shorter than the route's delay (400ms), and
    // max_retries is nonzero to prove a timeout is NOT retried into a
    // different outcome.
    let c = HttpChecker::new(Duration::from_millis(300), Duration::from_millis(80), 3);
    let outcome = c.check(&url);

    assert_eq!(
        outcome,
        CheckOutcome::Timeout,
        "a route delayed well past read_timeout must report Timeout and must not be retried \
         into some other outcome, got {outcome:?}"
    );
}
