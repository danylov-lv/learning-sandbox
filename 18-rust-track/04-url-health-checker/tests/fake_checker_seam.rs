//! Grades the injectable-`Checker` seam with a fake implemented entirely in
//! this test file: deterministic, no sockets, no fixture server. Proves the
//! pool's result classification, url<->outcome pairing, and aggregation --
//! independent of anything network-related -- and kills degenerate pool
//! implementations (drop work, duplicate work, mix up pairing, or collapse
//! every outcome to the same variant) directly.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use t04_url_health_checker::{check_urls_concurrently, CheckOutcome, Checker, HealthReport};

/// Pure, deterministic classification keyed off a marker substring in the
/// URL itself -- reused both inside the fake `Checker` and directly by
/// tests to build the expected result, so "expected" never depends on
/// calling the checker (or the pool) a second time.
fn classify(url: &str) -> CheckOutcome {
    if url.contains("unhealthy") {
        CheckOutcome::Unhealthy {
            status: 500,
            attempts: 1,
        }
    } else if url.contains("refused") {
        CheckOutcome::ConnectionFailed { attempts: 3 }
    } else if url.contains("timeout") {
        CheckOutcome::Timeout
    } else {
        CheckOutcome::Healthy {
            status: 200,
            attempts: 1,
        }
    }
}

struct FakeChecker {
    calls: Arc<AtomicUsize>,
}

impl Checker for FakeChecker {
    fn check(&self, url: &str) -> CheckOutcome {
        self.calls.fetch_add(1, Ordering::SeqCst);
        classify(url)
    }
}

fn fixed_input() -> Vec<String> {
    vec![
        "http://fake/healthy-1".to_string(),
        "http://fake/unhealthy-1".to_string(),
        "http://fake/refused-1".to_string(),
        "http://fake/timeout-1".to_string(),
        "http://fake/healthy-2".to_string(),
        "http://fake/unhealthy-2".to_string(),
        "http://fake/healthy-3".to_string(),
    ]
}

#[test]
fn every_report_is_correctly_paired_with_its_own_url_classification() {
    let checker = FakeChecker {
        calls: Arc::new(AtomicUsize::new(0)),
    };
    let input = fixed_input();

    let mut reports = check_urls_concurrently(&checker, &input, 3);
    reports.sort_by(|a, b| a.url.cmp(&b.url));

    let mut expected: Vec<HealthReport> = input
        .iter()
        .map(|u| HealthReport {
            url: u.clone(),
            outcome: classify(u),
        })
        .collect();
    expected.sort_by(|a, b| a.url.cmp(&b.url));

    assert_eq!(
        reports, expected,
        "every URL must come back through the pool with exactly the outcome `classify` \
         deterministically produces for it, correctly paired to that same URL -- a pool that \
         mixes up which result belongs to which URL, or drops/duplicates entries, fails here \
         even though no socket was ever opened"
    );
}

#[test]
fn pool_calls_the_checker_exactly_once_per_url() {
    let calls = Arc::new(AtomicUsize::new(0));
    let checker = FakeChecker {
        calls: calls.clone(),
    };
    let input = fixed_input();

    let reports = check_urls_concurrently(&checker, &input, 3);

    assert_eq!(
        reports.len(),
        input.len(),
        "expected exactly one HealthReport per submitted URL ({}), got {}",
        input.len(),
        reports.len()
    );
    assert_eq!(
        calls.load(Ordering::SeqCst),
        input.len(),
        "the checker must be invoked exactly once per URL; more calls suggests duplicated \
         work, fewer suggests dropped work -- neither is observable from total report count \
         alone if a report were fabricated instead of collected"
    );
}

#[test]
fn distinct_outcome_variants_all_survive_the_round_trip_through_the_pool() {
    // A degenerate pool/checker interaction that reports everything Healthy
    // (or returns a single hardcoded outcome) fails every assertion below
    // except at most one.
    let checker = FakeChecker {
        calls: Arc::new(AtomicUsize::new(0)),
    };
    let input = fixed_input();

    let reports = check_urls_concurrently(&checker, &input, 2);

    let healthy = reports
        .iter()
        .filter(|r| matches!(r.outcome, CheckOutcome::Healthy { .. }))
        .count();
    let unhealthy = reports
        .iter()
        .filter(|r| matches!(r.outcome, CheckOutcome::Unhealthy { .. }))
        .count();
    let failed = reports
        .iter()
        .filter(|r| matches!(r.outcome, CheckOutcome::ConnectionFailed { .. }))
        .count();
    let timed_out = reports
        .iter()
        .filter(|r| matches!(r.outcome, CheckOutcome::Timeout))
        .count();

    assert_eq!(healthy, 3, "expected 3 Healthy outcomes in the fixed input, got {healthy}");
    assert_eq!(unhealthy, 2, "expected 2 Unhealthy outcomes in the fixed input, got {unhealthy}");
    assert_eq!(failed, 1, "expected 1 ConnectionFailed outcome in the fixed input, got {failed}");
    assert_eq!(timed_out, 1, "expected 1 Timeout outcome in the fixed input, got {timed_out}");
}

#[test]
fn works_with_more_urls_than_workers() {
    // worker_count (2) smaller than input length (7) forces the pool to
    // actually reuse workers across multiple queue items, not just spawn
    // one thread per URL and call it a pool.
    let checker = FakeChecker {
        calls: Arc::new(AtomicUsize::new(0)),
    };
    let input = fixed_input();

    let reports = check_urls_concurrently(&checker, &input, 2);

    assert_eq!(
        reports.len(),
        input.len(),
        "a pool with fewer workers than URLs must still process every URL exactly once, got {} \
         reports for {} URLs",
        reports.len(),
        input.len()
    );
}
