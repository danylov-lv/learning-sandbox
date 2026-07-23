// @t3/worker — the job consumer.
//
// Two stages, both round-tripping through @t3/contracts types only:
//
//   1. receiveJobMessage: an untyped payload (as it would arrive off a
//      queue) in, a contract-typed JobMessage or a typed JobError out —
//      never a thrown exception for a malformed/unknown-version envelope.
//   2. processJob: a validated JobMessage in, a contract-typed JobResult
//      out, via an EXHAUSTIVE switch over `job.kind`. That exhaustiveness
//      is this task's anti-drift lever: implement it with a `default`
//      branch that calls an `assertNever` helper (see hint-2/hint-3), and
//      adding or renaming a kind in @t3/contracts without updating this
//      function breaks THIS package's own typecheck at that line — not a
//      downstream test, not a runtime surprise.

import type { JobError, JobMessage, JobResult } from "@t3/contracts";

/**
 * Outcome of validating a raw, untyped payload against
 * `JobMessageSchema.safeParse(...)`.
 */
export type ReceiveResult = { ok: true; job: JobMessage } | { ok: false; error: JobError };

/**
 * Parses `raw` against @t3/contracts' JobMessageSchema. An unknown `kind`,
 * a known `kind` with the wrong `version`, or any other structurally-
 * invalid payload (including non-object values) must come back as
 * `{ ok: false, error }` — never throw, never crash the caller. Only a
 * genuinely valid, versioned envelope comes back as `{ ok: true, job }`.
 *
 * `error.jobId` recovery rule, pinned exactly: if `raw` is a non-null
 * object with a string `jobId` field, `error.jobId` is that string;
 * otherwise it's `null`. This lets a caller correlate a rejected message
 * back to its origin whenever that's actually possible, without pretending
 * it's always possible.
 */
export function receiveJobMessage(raw: unknown): ReceiveResult {
  throw new Error(`not implemented: receiveJobMessage(${JSON.stringify(raw)})`);
}

/**
 * Consumes one validated job message and produces its contract-typed
 * result. Business rules, pinned exactly (CP2 checks these against hand-
 * computed expected values):
 *
 * `product.enrich` -> ProductEnrichResult
 *   normalizedSku = payload.sku.trim().toUpperCase()
 *   priceTier = payload.price < 50     ? "budget"
 *             : payload.price < 500    ? "standard"
 *             :                          "premium"
 *
 * `product.reprice` -> ProductRepriceResult
 *   newPrice = round(payload.currentPrice * (1 + payload.adjustmentPct / 100)
 *                     to 2 decimal places)
 *
 * Implement this as an exhaustive switch over `job.kind`; see this file's
 * top comment for why that exhaustiveness matters.
 */
export function processJob(job: JobMessage): JobResult {
  throw new Error(`not implemented: processJob(${JSON.stringify(job)})`);
}
