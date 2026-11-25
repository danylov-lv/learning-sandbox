// @t3/contracts — the versioned job-message envelope.
//
// @t3/worker consumes messages of this shape (imagine them arriving off a
// queue, though this task never wires an actual queue — @t3/e2e's CP2
// constructs envelopes directly as `unknown` values, the same way a
// deserialized queue message would arrive). Two things make this a real
// "contract", not just a type alias:
//
//   1. Every envelope carries a `version` literal per `kind`, so a future
//      `product.enrich` v2 payload can be added as its own union member
//      without breaking v1 consumers — see hint-2 for the shape.
//   2. The union is discriminated on `kind`, so an unknown kind or a known
//      kind with the wrong version both fail to parse instead of silently
//      matching the wrong branch.

import { z } from "zod";

/**
 * The set of job kinds this system currently knows about. A literal
 * union, not derived from JobMessageSchema below, so it stays meaningful
 * on its own. Add a new kind here FIRST, before wiring its schema and its
 * worker handler — that ordering is what gives @t3/worker's exhaustive
 * switch (see hint-2/hint-3) something concrete to fail against when a
 * kind is added or renamed without the worker being updated to handle it.
 */
export type JobKind = "product.enrich" | "product.reprice";

/**
 * v1 envelope for "normalize this product's sku and classify its price
 * tier":
 *
 *   {
 *     kind: "product.enrich";
 *     version: 1;
 *     jobId: string;
 *     payload: { productId: number; sku: string; price: number };
 *   }
 */
export const ProductEnrichJobV1Schema = z.unknown();
export type ProductEnrichJobV1 = z.infer<typeof ProductEnrichJobV1Schema>;

/**
 * v1 envelope for "recompute this product's price after a percentage
 * adjustment":
 *
 *   {
 *     kind: "product.reprice";
 *     version: 1;
 *     jobId: string;
 *     payload: { productId: number; currentPrice: number; adjustmentPct: number };
 *   }
 */
export const ProductRepriceJobV1Schema = z.unknown();
export type ProductRepriceJobV1 = z.infer<typeof ProductRepriceJobV1Schema>;

/**
 * The job-message envelope: a discriminated union over `kind`. Replace the
 * z.unknown() placeholder with
 * `z.discriminatedUnion("kind", [ProductEnrichJobV1Schema, ProductRepriceJobV1Schema])`.
 */
export const JobMessageSchema = z.unknown();
export type JobMessage = z.infer<typeof JobMessageSchema>;

/**
 * Result of a successful `product.enrich` job:
 *
 *   { productId: number; normalizedSku: string; priceTier: "budget" | "standard" | "premium" }
 */
export const ProductEnrichResultSchema = z.unknown();
export type ProductEnrichResult = z.infer<typeof ProductEnrichResultSchema>;

/**
 * Result of a successful `product.reprice` job:
 *
 *   { productId: number; newPrice: number }
 */
export const ProductRepriceResultSchema = z.unknown();
export type ProductRepriceResult = z.infer<typeof ProductRepriceResultSchema>;

/**
 * A worker's successful output, tagged the same way as the input envelope
 * (a discriminated union over `kind`) so a consumer can narrow on `kind`
 * the same way it narrowed the job:
 *
 *   | { kind: "product.enrich"; jobId: string; result: ProductEnrichResult }
 *   | { kind: "product.reprice"; jobId: string; result: ProductRepriceResult }
 */
export const JobResultSchema = z.unknown();
export type JobResult = z.infer<typeof JobResultSchema>;

/**
 * Typed rejection for a malformed or unknown-version envelope — this is
 * what @t3/worker's `receiveJobMessage` returns instead of throwing.
 * `jobId` is `null` when it couldn't even be recovered from the raw input:
 *
 *   { jobId: string | null; reason: string }
 */
export const JobErrorSchema = z.unknown();
export type JobError = z.infer<typeof JobErrorSchema>;
