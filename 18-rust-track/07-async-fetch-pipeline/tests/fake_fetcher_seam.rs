//! Grades the injectable-`Fetcher` seam with fakes implemented entirely in
//! this test file: deterministic, no sockets, no fixture server. Proves the
//! pipeline's result classification, url<->outcome pairing, all four
//! `FetchOutcome` variants surviving the round trip, and cooperative
//! shutdown -- independent of anything network-related. A degenerate
//! pipeline (drops work, duplicates work, mixes up pairing, collapses every
//! outcome to the same variant, or ignores the shutdown signal) fails these
//! directly.

use std::sync::Arc;
use std::time::Duration;

use t07_async_fetch_pipeline::{
    FetchOutcome, FetchReport, Fetcher, PipelineConfig, PipelineHandle, PipelineOutcome,
    ShutdownSignal, spawn_pipeline,
};

/// Drains every report off the pipeline's bounded channel, then awaits
/// `join`. The recv loop only ends once every spawned task has dropped its
/// sender clone (i.e. exited, cancelled or not), so calling `join` after it
/// returns proves nothing is left racing the channel close.
async fn drain_and_join(mut handle: PipelineHandle) -> (PipelineOutcome, Vec<FetchReport>) {
    let mut reports = Vec::new();
    while let Some(report) = handle.receiver.recv().await {
        reports.push(report);
    }
    (handle.join().await, reports)
}

/// Same as `drain_and_join`, wrapped in a generous safety timeout -- not a
/// grading signal, just protection against a broken implementation hanging
/// the whole test binary instead of failing with a message.
async fn drain_and_join_with_timeout(handle: PipelineHandle) -> (PipelineOutcome, Vec<FetchReport>) {
    tokio::time::timeout(Duration::from_secs(5), drain_and_join(handle))
        .await
        .expect(
            "the pipeline did not finish within the safety timeout -- this indicates a hang \
             (e.g. shutdown not honored, or a task stuck holding a permit), not a timing grade",
        )
}

/// Pure, deterministic classification keyed off a marker substring in the
/// URL itself -- reused both inside the fake `Fetcher` and directly by tests
/// to build the expected result, so "expected" never depends on calling the
/// fetcher (or the pipeline) a second time.
fn classify(url: &str) -> FetchOutcome {
    if url.contains("unhealthy") {
        FetchOutcome::Unhealthy {
            status: 500,
            attempts: 1,
        }
    } else if url.contains("connfail") {
        FetchOutcome::ConnectionFailed { attempts: 3 }
    } else if url.contains("timeout") {
        FetchOutcome::Timeout
    } else {
        FetchOutcome::Healthy {
            status: 200,
            attempts: 1,
        }
    }
}

struct ClassifyingFetcher;

impl Fetcher for ClassifyingFetcher {
    async fn fetch(&self, url: &str) -> FetchOutcome {
        classify(url)
    }
}

fn fixed_input() -> Vec<String> {
    vec![
        "http://fake/healthy-1",
        "http://fake/unhealthy-1",
        "http://fake/connfail-1",
        "http://fake/timeout-1",
        "http://fake/healthy-2",
        "http://fake/unhealthy-2",
        "http://fake/healthy-3",
    ]
    .into_iter()
    .map(String::from)
    .collect()
}

#[tokio::test]
async fn every_report_is_correctly_paired_with_its_own_url_classification() {
    let fetcher = Arc::new(ClassifyingFetcher);
    let input = fixed_input();
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: 3,
        channel_capacity: 8,
    };

    let handle = spawn_pipeline(fetcher, input.clone(), config, shutdown_rx);
    let (outcome, mut reports) = drain_and_join_with_timeout(handle).await;

    assert_eq!(
        outcome.tasks_spawned,
        input.len(),
        "tasks_spawned must equal urls.len() regardless of how fetches classify, got {}",
        outcome.tasks_spawned
    );
    assert!(
        !outcome.cancelled,
        "shutdown was never signalled, so cancelled must be false"
    );

    reports.sort_by(|a, b| a.url.cmp(&b.url));
    let mut expected: Vec<FetchReport> = input
        .iter()
        .map(|u| FetchReport {
            url: u.clone(),
            outcome: classify(u),
        })
        .collect();
    expected.sort_by(|a, b| a.url.cmp(&b.url));

    assert_eq!(
        reports, expected,
        "every URL must come back through the pipeline with exactly the outcome `classify` \
         deterministically produces for it, correctly paired to that same URL -- a pipeline \
         that mixes up which result belongs to which URL, or drops/duplicates entries, fails \
         here even though no socket was ever opened"
    );
}

#[tokio::test]
async fn all_four_outcome_variants_survive_the_round_trip() {
    // A degenerate pipeline that reports everything Healthy (or returns a
    // single hardcoded outcome) fails every assertion below except at most
    // one.
    let fetcher = Arc::new(ClassifyingFetcher);
    let input = fixed_input();
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: 2,
        channel_capacity: 2,
    };

    let handle = spawn_pipeline(fetcher, input.clone(), config, shutdown_rx);
    let (_outcome, reports) = drain_and_join_with_timeout(handle).await;

    assert_eq!(
        reports.len(),
        input.len(),
        "expected exactly one FetchReport per submitted URL ({}), got {}",
        input.len(),
        reports.len()
    );

    let healthy = reports
        .iter()
        .filter(|r| matches!(r.outcome, FetchOutcome::Healthy { .. }))
        .count();
    let unhealthy = reports
        .iter()
        .filter(|r| matches!(r.outcome, FetchOutcome::Unhealthy { .. }))
        .count();
    let connection_failed = reports
        .iter()
        .filter(|r| matches!(r.outcome, FetchOutcome::ConnectionFailed { .. }))
        .count();
    let timed_out = reports
        .iter()
        .filter(|r| matches!(r.outcome, FetchOutcome::Timeout))
        .count();

    assert_eq!(healthy, 3, "expected 3 Healthy outcomes in the fixed input, got {healthy}");
    assert_eq!(unhealthy, 2, "expected 2 Unhealthy outcomes in the fixed input, got {unhealthy}");
    assert_eq!(
        connection_failed, 1,
        "expected 1 ConnectionFailed outcome in the fixed input, got {connection_failed}"
    );
    assert_eq!(timed_out, 1, "expected 1 Timeout outcome in the fixed input, got {timed_out}");
}

#[tokio::test]
async fn works_with_more_urls_than_the_concurrency_cap() {
    // concurrency_cap (2) smaller than input length (7) forces the pipeline
    // to actually reuse permits across multiple URLs, not just spawn
    // everything at once and call it capped.
    let fetcher = Arc::new(ClassifyingFetcher);
    let input = fixed_input();
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: 2,
        channel_capacity: 1,
    };

    let handle = spawn_pipeline(fetcher, input.clone(), config, shutdown_rx);
    let (outcome, reports) = drain_and_join_with_timeout(handle).await;

    assert_eq!(
        reports.len(),
        input.len(),
        "a pipeline with fewer permits than URLs must still process every URL exactly once, \
         got {} reports for {} URLs",
        reports.len(),
        input.len()
    );
    assert_eq!(outcome.tasks_spawned, input.len(), "tasks_spawned must equal urls.len()");
}

/// A fetch that never resolves on its own -- any report at all from this
/// fetcher would mean the pipeline let a fetch complete instead of
/// cancelling it, so every assertion below is deterministic: shutdown must
/// win the race every single time, never the fetch.
struct NeverResolvingFetcher;

impl Fetcher for NeverResolvingFetcher {
    async fn fetch(&self, _url: &str) -> FetchOutcome {
        std::future::pending::<()>().await;
        unreachable!("this fetch must never be allowed to complete on its own")
    }
}

#[tokio::test]
async fn cooperative_shutdown_cancels_everything_and_leaves_nothing_running() {
    const URL_COUNT: usize = 10;

    let fetcher = Arc::new(NeverResolvingFetcher);
    let urls: Vec<String> = (0..URL_COUNT).map(|i| format!("http://fake/{i}")).collect();
    let (signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: 3,
        channel_capacity: 4,
    };

    let handle = spawn_pipeline(fetcher, urls, config, shutdown_rx);

    // Give the pipeline a chance to actually start work (acquire permits,
    // enter fetch, block other tasks on the permit) before cancelling, so
    // shutdown has real in-flight work to interrupt rather than an empty
    // pipeline that trivially finishes.
    tokio::task::yield_now().await;
    signal.cancel();

    let (outcome, reports) = drain_and_join_with_timeout(handle).await;

    assert!(
        reports.is_empty(),
        "every fetch in this test blocks forever unless cancelled, so no FetchReport should \
         ever have been produced; got {} reports: {reports:?}",
        reports.len()
    );
    assert_eq!(
        outcome.tasks_spawned, URL_COUNT,
        "tasks_spawned must still equal urls.len() even when the run was cut short by shutdown, \
         got {}",
        outcome.tasks_spawned
    );
    assert!(
        outcome.cancelled,
        "cancelled must be true once the shutdown signal was observed cancelled"
    );
}

#[tokio::test]
async fn shutdown_cancelled_before_spawn_still_completes_cleanly() {
    // Cancel the signal before the pipeline is even spawned -- every task
    // should observe it immediately (permit-acquire branch of the select!
    // loses to shutdown.cancelled() right away) and the whole run should
    // still account for every URL without ever calling fetch.
    const URL_COUNT: usize = 5;

    let fetcher = Arc::new(NeverResolvingFetcher);
    let urls: Vec<String> = (0..URL_COUNT).map(|i| format!("http://fake/{i}")).collect();
    let (signal, shutdown_rx) = ShutdownSignal::new();
    signal.cancel();

    let config = PipelineConfig {
        concurrency_cap: 2,
        channel_capacity: 2,
    };
    let handle = spawn_pipeline(fetcher, urls, config, shutdown_rx);
    let (outcome, reports) = drain_and_join_with_timeout(handle).await;

    assert!(
        reports.is_empty(),
        "shutdown was already cancelled before spawn_pipeline was even called, so not a single \
         fetch should have run: got {reports:?}"
    );
    assert_eq!(outcome.tasks_spawned, URL_COUNT, "tasks_spawned must still equal urls.len()");
    assert!(outcome.cancelled, "cancelled must be true when the signal was already cancelled");
}
