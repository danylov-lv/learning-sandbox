"""t08 -- a live async worker to profile with py-spy.

This is a small event-ingestion service: records arrive, get parsed,
looked up against a (simulated) context store, normalized into a stable
shape, and persisted. It is written the way an on-call engineer would find
it in a real repo -- several small pipeline steps, a bounded producer/
consumer queue, `asyncio.TaskGroup` for the worker pool, nothing that looks
obviously wrong on a skim.

It is also slow in a way that doesn't show up by reading the source. Run it
and watch: throughput is far below what the concurrency setting and the
simulated I/O latency alone would predict, and anything else sharing the
process (a health-check endpoint, a metrics exporter, this file's own
progress ticker) stalls in bursts instead of ticking smoothly. That symptom
-- "async code that behaves like it's single-threaded serial" -- has one
usual cause: something in the pipeline is doing real CPU work directly on
the event loop thread instead of yielding it. Where, specifically, is not
handed to you here. Find it the way you would in production: attach a
sampling profiler (`py-spy`) to the *running* process and look at where the
samples pile up. Reading the diff between functions is not the intended
path -- there is no docstring in this file that names the culprit.

Run it directly to start a long-lived process you can attach a profiler to:

    uv run python src/app.py

It prints its PID immediately, then runs until `--duration` seconds have
elapsed (or `--records` records have been processed, if `--duration` is not
given) -- long enough to open a second terminal and attach py-spy before it
exits. It also imports cleanly and exposes `run_workload(...)` as a plain
async function, so it can be driven directly (no subprocess) by anything
that wants to measure the pipeline's behavior in-process, e.g. a test
harness checking whether the event loop stayed responsive while it ran.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import time

FETCH_LATENCY = 0.01
PERSIST_LATENCY = 0.01


# --------------------------------------------------------------------------
# Calibration -- normalize the pipeline's CPU-bound step to real wall-clock
# time on whatever machine this runs on, rather than a fixed iteration count
# that would be trivial on a fast box and glacial on a slow one.
# --------------------------------------------------------------------------

def _calibrate_iters(target_seconds=0.008, sample_iters=200_000):
    start = time.perf_counter()
    x = 0
    for i in range(sample_iters):
        x = (x * 1_000_003 + i) & 0xFFFFFFFF
    elapsed = time.perf_counter() - start
    if elapsed <= 0:
        return sample_iters * 20
    return max(sample_iters, int(sample_iters * (target_seconds / elapsed)))


_SIGNATURE_ITERS = _calibrate_iters()


# --------------------------------------------------------------------------
# Pipeline steps -- several small, plausible-looking helpers. Exactly one of
# them is the bottleneck; the others are here because a real pipeline has
# several steps that all look about as busy as each other on a skim.
# --------------------------------------------------------------------------

def _make_raw_record(record_id: int) -> bytes:
    payload = {
        "id": record_id,
        "source": "ingest-worker",
        "body": f"event-{record_id}-{'payload' * 4}",
    }
    return json.dumps(payload).encode()


def _parse_payload(raw: bytes) -> dict:
    return json.loads(raw.decode())


def _checksum_header(evt: dict) -> int:
    """Cheap sanity checksum over a few header bytes -- fast, on purpose."""
    header = f"{evt['id']}:{evt['source']}".encode()
    x = 0
    for b in header[:16]:
        x = (x * 31 + b) & 0xFFFF
    return x


def _validate_event(evt: dict) -> bool:
    return isinstance(evt.get("id"), int) and bool(evt.get("body"))


def compute_signature(evt: dict) -> str:
    """Derive a stable content signature for this event, used downstream
    for idempotent writes and dedup lookups against the context store."""
    body = evt["body"].encode()
    x = 0
    for b in body[:64]:
        x = (x * 31 + b) & 0xFFFFFFFF
    for i in range(_SIGNATURE_ITERS):
        x = (x * 1_000_003 + i) & 0xFFFFFFFF
    return f"{x:08x}"


def _enrich_event(evt: dict, signature: str, checksum: int) -> dict:
    return {**evt, "signature": signature, "checksum": checksum}


def _serialize_event(evt: dict) -> bytes:
    return json.dumps(evt).encode()


async def _simulate_context_lookup(latency: float) -> None:
    await asyncio.sleep(latency)


async def _simulate_persist(payload: bytes, latency: float) -> None:
    await asyncio.sleep(latency)


async def process_one(record_id: int, fetch_latency: float, persist_latency: float) -> dict:
    raw = _make_raw_record(record_id)
    evt = _parse_payload(raw)

    await _simulate_context_lookup(fetch_latency)

    if not _validate_event(evt):
        raise ValueError(f"invalid event: {evt!r}")

    checksum = _checksum_header(evt)
    signature = compute_signature(evt)
    enriched = _enrich_event(evt, signature, checksum)
    payload = _serialize_event(enriched)

    await _simulate_persist(payload, persist_latency)
    return enriched


# --------------------------------------------------------------------------
# Importable entrypoint -- bounded producer/consumer, TaskGroup worker pool.
# --------------------------------------------------------------------------

async def run_workload(
    n_records: int | None = None,
    *,
    concurrency: int = 8,
    duration: float | None = None,
    fetch_latency: float = FETCH_LATENCY,
    persist_latency: float = PERSIST_LATENCY,
) -> dict:
    """Process records with `concurrency` concurrent workers pulling off a
    bounded queue. Either `n_records` (process exactly this many) or
    `duration` (keep generating and processing until this many seconds have
    elapsed) must be given; `duration` wins if both are set.

    Returns `{"records_processed": int, "errors": int, "elapsed_seconds": float}`.
    """
    if duration is None and n_records is None:
        raise ValueError("run_workload requires n_records or duration")

    queue: asyncio.Queue = asyncio.Queue(maxsize=concurrency * 2)
    stats = {"records_processed": 0, "errors": 0}
    started = time.perf_counter()

    async def _producer():
        i = 0
        while True:
            if duration is not None:
                if time.perf_counter() - started >= duration:
                    break
            elif i >= n_records:
                break
            await queue.put(i)
            i += 1
        for _ in range(concurrency):
            await queue.put(None)

    async def _consumer():
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                try:
                    await process_one(item, fetch_latency, persist_latency)
                    stats["records_processed"] += 1
                except ValueError:
                    stats["errors"] += 1
            finally:
                queue.task_done()

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_producer())
        for _ in range(concurrency):
            tg.create_task(_consumer())

    stats["elapsed_seconds"] = time.perf_counter() - started
    return stats


# --------------------------------------------------------------------------
# CLI entrypoint -- a long-lived process to attach py-spy to.
# --------------------------------------------------------------------------

async def _heartbeat_ticker(interval: float = 1.0):
    tick = 0
    start = time.perf_counter()
    while True:
        await asyncio.sleep(interval)
        tick += 1
        print(f"[heartbeat] tick={tick} elapsed={time.perf_counter() - start:.1f}s", flush=True)


async def _run_cli(args: argparse.Namespace) -> dict:
    print(f"PID={os.getpid()}", flush=True)
    mode = f"duration={args.duration}s" if args.duration is not None else f"records={args.records}"
    print(f"starting ingest worker: {mode} concurrency={args.concurrency}", flush=True)

    ticker = asyncio.create_task(_heartbeat_ticker())
    try:
        stats = await run_workload(
            n_records=args.records if args.duration is None else None,
            concurrency=args.concurrency,
            duration=args.duration,
            fetch_latency=args.fetch_latency,
            persist_latency=args.persist_latency,
        )
    finally:
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ticker

    print(f"done: {stats}", flush=True)
    return stats


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Async event-ingestion worker (py-spy profiling target).")
    p.add_argument("--records", type=int, default=2500, help="records to process (ignored if --duration is set)")
    p.add_argument("--concurrency", type=int, default=12, help="number of concurrent consumer workers")
    p.add_argument("--duration", type=float, default=None, help="run for this many seconds instead of a fixed count")
    p.add_argument("--fetch-latency", type=float, default=FETCH_LATENCY, dest="fetch_latency")
    p.add_argument("--persist-latency", type=float, default=PERSIST_LATENCY, dest="persist_latency")
    return p


def main(argv=None) -> None:
    args = _build_arg_parser().parse_args(argv)
    asyncio.run(_run_cli(args))


if __name__ == "__main__":
    main()
