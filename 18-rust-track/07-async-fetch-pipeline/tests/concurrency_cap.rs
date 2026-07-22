//! Grades `PipelineConfig::concurrency_cap` and `channel_capacity`
//! STRUCTURALLY, against counters a fake `Fetcher` tracks about itself --
//! never against wall-clock elapsed time. `tokio::sync::Barrier` forces
//! deterministic overlap (a fixed number of fetches really are in flight at
//! once) instead of hoping a `sleep` duration happens to line up; the
//! backpressure test never drains the channel at all and instead waits,
//! via cooperative yields, for the fetch stage to reach the one steady
//! state it structurally can reach, then asserts on how far "ahead" that
//! steady state actually is.

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use tokio::sync::Barrier;
use t07_async_fetch_pipeline::{FetchOutcome, Fetcher, PipelineConfig, ShutdownSignal, spawn_pipeline};

/// Tracks live and max-ever-live concurrent `fetch` calls via plain
/// `AtomicUsize`s (independent of anything the pipeline itself reports),
/// and rendezvouses at a `Barrier` sized to the expected cap so that "the
/// cap was reached" is a deterministic event, not a timing gamble.
struct GatedFetcher {
    live: AtomicUsize,
    max_live: AtomicUsize,
    barrier: Barrier,
}

impl GatedFetcher {
    fn new(cap: usize) -> Self {
        Self {
            live: AtomicUsize::new(0),
            max_live: AtomicUsize::new(0),
            barrier: Barrier::new(cap),
        }
    }
}

impl Fetcher for GatedFetcher {
    async fn fetch(&self, _url: &str) -> FetchOutcome {
        let live = self.live.fetch_add(1, Ordering::SeqCst) + 1;
        self.max_live.fetch_max(live, Ordering::SeqCst);
        // Only releases once exactly `cap` fetches have arrived here at
        // once -- a pipeline that under-parallelizes (never gets `cap`
        // fetches concurrently in flight) deadlocks this instead of
        // silently passing, which is exactly why the whole test is wrapped
        // in a safety timeout below rather than allowed to hang forever.
        self.barrier.wait().await;
        self.live.fetch_sub(1, Ordering::SeqCst);
        FetchOutcome::Healthy {
            status: 200,
            attempts: 1,
        }
    }
}

#[tokio::test]
async fn concurrency_cap_is_reached_but_never_exceeded() {
    const CAP: usize = 4;
    const URL_COUNT: usize = CAP * 3; // multiple of CAP: every barrier generation completes

    let fetcher = Arc::new(GatedFetcher::new(CAP));
    let urls: Vec<String> = (0..URL_COUNT).map(|i| format!("http://fake/{i}")).collect();
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: CAP,
        channel_capacity: 2,
    };

    let mut handle = spawn_pipeline(Arc::clone(&fetcher), urls, config, shutdown_rx);

    let run = async move {
        let mut reports = Vec::new();
        while let Some(report) = handle.receiver.recv().await {
            reports.push(report);
        }
        (handle.join().await, reports)
    };

    let (outcome, reports) = tokio::time::timeout(Duration::from_secs(5), run)
        .await
        .expect(
            "the pipeline did not finish within the safety timeout -- a pipeline that never \
             lets `concurrency_cap` fetches run at once will deadlock the barrier used to force \
             deterministic overlap; this is a hang, not a timing grade",
        );

    assert_eq!(
        reports.len(),
        URL_COUNT,
        "every submitted URL must produce exactly one report, got {}",
        reports.len()
    );
    assert_eq!(outcome.tasks_spawned, URL_COUNT, "tasks_spawned must equal urls.len()");

    let max_observed = fetcher.max_live.load(Ordering::SeqCst);
    assert!(
        max_observed <= CAP,
        "concurrency_cap={CAP} is a HARD cap: the fake fetcher observed max_live={max_observed}, \
         which must never exceed it -- a pipeline with no real cap (or a semaphore sized wrong) \
         would blow past this"
    );
    assert!(
        max_observed >= CAP,
        "with {URL_COUNT} urls (3x the cap) and a barrier that only releases once `cap` fetches \
         rendezvous concurrently, a genuinely parallel pipeline must drive max_live all the way \
         up to {CAP}; observed max_live={max_observed} means the pipeline under-parallelizes"
    );
}

/// A fetch that returns immediately after recording that it started -- the
/// bottleneck this test is designed to expose lives entirely inside
/// `spawn_pipeline`'s send-to-the-bounded-channel step, not inside `fetch`
/// itself.
struct CountingFetcher {
    started: AtomicUsize,
}

impl Fetcher for CountingFetcher {
    async fn fetch(&self, _url: &str) -> FetchOutcome {
        self.started.fetch_add(1, Ordering::SeqCst);
        FetchOutcome::Healthy {
            status: 200,
            attempts: 1,
        }
    }
}

/// Cooperatively yields until `counter` stops changing for several
/// consecutive polls. Once a pipeline with nobody draining its channel
/// truly reaches its structural ceiling (every permit either held by a task
/// blocked on a full channel, or exhausted outright), the counter provably
/// cannot increase again without external input -- so "stable for N polls
/// in a row" is a correctness fact here, not a heuristic about timing.
async fn settle(counter: &AtomicUsize) -> usize {
    let mut last = counter.load(Ordering::SeqCst);
    let mut stable_polls = 0;
    for _ in 0..20_000 {
        tokio::task::yield_now().await;
        let now = counter.load(Ordering::SeqCst);
        if now == last {
            stable_polls += 1;
            if stable_polls >= 100 {
                return now;
            }
        } else {
            last = now;
            stable_polls = 0;
        }
    }
    panic!(
        "counter never stabilized after many cooperative yields -- last observed value {last}"
    );
}

#[tokio::test]
async fn bounded_channel_provides_backpressure_on_the_fetch_stage() {
    const CAP: usize = 2; // concurrency_cap
    const CHANNEL: usize = 2; // channel_capacity
    const URL_COUNT: usize = 20; // far more than CAP + CHANNEL

    let fetcher = Arc::new(CountingFetcher {
        started: AtomicUsize::new(0),
    });
    let urls: Vec<String> = (0..URL_COUNT).map(|i| format!("http://fake/{i}")).collect();
    let (_signal, shutdown_rx) = ShutdownSignal::new();
    let config = PipelineConfig {
        concurrency_cap: CAP,
        channel_capacity: CHANNEL,
    };

    // `handle` (and its receiver) is deliberately never drained: that's the
    // entire point of this test. It's also never joined, since a full
    // channel with nobody consuming it means some permits are legitimately
    // stuck forever -- joining would hang by design, not by bug.
    let handle = spawn_pipeline(fetcher.clone(), urls, config, shutdown_rx);

    let started = tokio::time::timeout(Duration::from_secs(5), settle(&fetcher.started))
        .await
        .expect("the started-fetch counter never stabilized within the safety timeout");

    assert!(
        started <= CAP + CHANNEL,
        "with no consumer ever draining the channel, at most concurrency_cap ({CAP}) fetches \
         can be blocked holding a permit while trying to send, plus channel_capacity ({CHANNEL}) \
         already buffered in the channel -- observed {started} started fetches means the fetch \
         stage ran ahead of the bound, so the bounded channel is not providing real backpressure"
    );
    assert!(
        started >= CAP,
        "the fetch stage should still make progress up to the concurrency cap even with a full, \
         undrained channel; observed only {started} started fetches, suggesting it stalled \
         short of the cap"
    );

    drop(handle);
}
